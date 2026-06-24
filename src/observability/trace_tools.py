"""툴/단계 트레이싱 헬퍼 — 테스트 1건을 'root → 단계 span → KOSIS·LLM span' 트리로.

LLM 호출은 traced_chat 이 이미 generation 으로 기록한다. 본 모듈은 그 위에:
  - span(name)          : 임의 블록(파이프라인 단계 등)을 span 으로 감싸는 컨텍스트매니저
  - instrument_kosis()  : KOSIS HTTP 호출(_HttpClient.get)을 런타임 패치해 span 으로 (툴 사용)
  - run_pipeline_traced : root span 아래 단계들을 순서대로 span 으로 감싸 실행(가장 흔한 패턴)
  - flush()             : 종료 전 전송(배치 SDK)

Langfuse 자격(LANGFUSE_*)이 없으면 SDK 가 비활성 → 모든 헬퍼가 graceful no-op.
중첩은 Langfuse(OTel) 컨텍스트 전파로 자동 — asyncio.to_thread 도 contextvars 를
복사하므로 to_thread 안의 KOSIS/LLM 호출이 단계 span 아래로 들어간다.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Awaitable, Callable, Iterable, Optional

from langfuse import get_client, observe  # noqa: F401 (observe 재노출)

__all__ = ["span", "instrument_kosis", "run_pipeline_traced", "flush", "observe"]


@contextmanager
def span(name: str, *, input: Any = None, metadata: Optional[dict] = None):
    """임의 블록을 Langfuse span 으로 감싼다(비활성 시 no-op). 관측 객체를 yield."""
    lf = get_client()
    with lf.start_as_current_observation(
        as_type="span", name=name, input=input, metadata=metadata or None,
    ) as obs:
        yield obs


_KOSIS_PATCHED = False


def instrument_kosis() -> None:
    """KOSIS 모든 HTTP 호출(_HttpClient.get)을 span 으로 기록하도록 런타임 패치.

    모듈을 수정하지 않고, 모든 KOSIS 호출이 통과하는 단일 지점만 감싼다. apiKey 는
    기록하지 않는다. 멱등(중복 패치 방지). 비활성 시 span 이 no-op 이라 오버헤드 미미.
    """
    global _KOSIS_PATCHED
    if _KOSIS_PATCHED:
        return
    from src.kosis import client as kc

    orig = kc._HttpClient.get

    def traced_get(self, url, params, **kw):
        endpoint = url.rsplit("/", 1)[-1]
        safe = {k: v for k, v in (params or {}).items() if k != "apiKey"}
        with span(f"kosis:{endpoint}", input=safe) as obs:
            rows = orig(self, url, params, **kw)
            try:
                obs.update(output={"rows": len(rows)})
            except Exception:  # 비활성/no-op 관측 방어
                pass
            return rows

    kc._HttpClient.get = traced_get
    _KOSIS_PATCHED = True


async def run_pipeline_traced(
    ms: Any,
    stages: Iterable[Callable[[Any], Awaitable[None]]],
    *,
    root_name: str,
    metadata: Optional[dict] = None,
) -> Optional[str]:
    """root span 아래 stages 를 순서대로 span 으로 감싸 실행. 실패 단계명+예외 반환(없으면 None).

    KOSIS span(instrument_kosis 필요)·LLM generation(traced_chat)은 단계 span 아래 자동 중첩.
    """
    instrument_kosis()
    with span(root_name, metadata=metadata):
        for i, fn in enumerate(stages, 1):
            with span(f"[{i}] {fn.__name__}"):
                try:
                    await fn(ms)
                except Exception as exc:  # noqa: BLE001 — 단계 실패를 트레이스에 남기고 보고
                    return f"{fn.__name__}: {exc}"
    return None


def flush() -> None:
    """배치된 트레이스를 전송(프로세스 종료 전 호출)."""
    try:
        get_client().flush()
    except Exception:
        pass
