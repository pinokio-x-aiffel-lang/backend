"""src/prompts/prompts.py → Langfuse Prompt Management 동기화 (idempotent).

각 프롬프트를 chat prompt 로 등록하고 `production` 라벨을 단다. 현재 production
버전과 내용이 같으면 건너뛰어 중복 버전을 만들지 않는다. 바뀌었으면 새 버전을 생성한다.
코드(prompts.py)가 원본이고, 이 스크립트가 Langfuse 쪽 버전을 코드에 맞춘다(접근 A).

실행(키 주입 필요):
    infisical run --env dev --path /LangFuse -- \
        uv run python infra/langfuse/sync_prompts.py
"""
from __future__ import annotations

from langfuse import get_client

from src.observability.prompt_registry import PROMPTS, as_chat_prompt
from src.observability.tracing import PROMPT_LABEL


def _current_messages(lf, name: str):
    """현재 production 버전의 messages(list[{role,content}]). 없으면 None."""
    try:
        p = lf.get_prompt(name, label=PROMPT_LABEL, type="chat", fallback=None)
    except Exception:
        return None
    return getattr(p, "prompt", None)


def _same(a, b) -> bool:
    def norm(msgs):
        return [(m.get("role"), m.get("content")) for m in (msgs or [])]

    return norm(a) == norm(b)


def main() -> None:
    lf = get_client()
    if not lf.auth_check():
        raise SystemExit(
            "Langfuse 인증 실패 — LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST 확인"
            " (infisical run --path /LangFuse -- ...)"
        )

    changed, unchanged = [], []
    for name in PROMPTS:
        new = as_chat_prompt(name)
        if _same(_current_messages(lf, name), new):
            unchanged.append(name)
            continue
        lf.create_prompt(
            name=name,
            type="chat",
            prompt=new,
            labels=[PROMPT_LABEL],
            commit_message="sync from src/prompts/prompts.py",
        )
        changed.append(name)

    lf.flush()
    print(f"[sync] 생성/갱신 {len(changed)}: {changed}")
    print(f"[sync] 변경없음 {len(unchanged)}: {unchanged}")


if __name__ == "__main__":
    main()
