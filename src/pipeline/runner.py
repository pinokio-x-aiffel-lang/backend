"""Pipeline — 단계 조립·실행, 이벤트 스트리밍.

단계 구현은 src/modules/ 에 단계당 1파일·1함수로 있고, 여기서 import 해 조립한다.
  - 각 함수 시그니처: (master_schema: MasterSchema) -> None (제자리 변경, 반환 없음)
  - 실패 시 raise → runner try/except 가 StepEvent(error) 로 변환·중단

Pipeline.run():
  - MasterSchema 하나를 만들어 단계들이 차례로 채운다 (직접 흐름)
  - 각 단계 시작/완료/오류를 StepEvent 로 yield
  - 전 단계 완료 후 ResultEvent yield
  - HTTP / SSE / Queue 등 전송 방식은 모름 → 호출자(verify_service)의 몫

HITL(create_hitl_task / save_hitl_feedback)은 선형 흐름 밖이라 run() 단계에 없다.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator

from src.modules.calculate_metric import calculate_metric
from src.modules.check_alignment import check_alignment
from src.modules.decide_verdict import decide_verdict
from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.generate_explanation import generate_explanation
from src.modules.load_article import load_article
from src.modules.normalize_claim import normalize_claim
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.pipeline.events import PipelineEvent, ResultEvent, StepEvent
from src.schemas.runtime import MasterSchema


# ── Pipeline ─────────────────────────────────────────────────────────────────

class Pipeline:
    async def run(self, content: str, on_step=None) -> AsyncGenerator[PipelineEvent, None]:
        master_schema = MasterSchema(content=content)

        async for ev in self._step(1, "기사 내용 확인", load_article, master_schema, on_step): yield ev
        async for ev in self._step(2, "클레임 추출", extract_statistical_claims, master_schema, on_step): yield ev
        async for ev in self._step(3, "한국어 수사 산술로 변환", normalize_claim, master_schema, on_step): yield ev
        async for ev in self._step(4, "KOSIS 통계표 n개 찾기", retrieve_kosis_candidates, master_schema, on_step): yield ev
        async for ev in self._step(5, "KOSIS 셀 값 조회", fetch_kosis_data, master_schema, on_step): yield ev
        async for ev in self._step(6, "통계 수치 비교 판단", calculate_metric, master_schema, on_step): yield ev
        async for ev in self._step(7, "통계수치와 문장의 정합성 판단", check_alignment, master_schema, on_step): yield ev
        async for ev in self._step(8, "종합 분석·검증 결과 생성", decide_verdict, master_schema, on_step): yield ev
        async for ev in self._step(9, "설명 생성", generate_explanation, master_schema, on_step): yield ev

        yield ResultEvent(master_schema=master_schema)

    async def _step(self, step, name, fn, master_schema, on_step=None) -> AsyncGenerator[PipelineEvent, None]:
        t0 = time.monotonic()
        yield StepEvent(step=step, name=name, status="running")
        await asyncio.sleep(0.01)  # TEMP(ngrok SSE 테스트): 더미가 즉시 끝나 이벤트가 한 버스트로 몰리는 것 방지. 검증 후 제거.

        try:
            await fn(master_schema)
        except Exception as e:
            yield StepEvent(
                step=step, name=name, status="error",
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=str(e),
            )
            raise
        
        duration_ms = int((time.monotonic() - t0) * 1000)
        if on_step is not None:
            on_step(step, name, master_schema)

        # 멈췄다 재개하며 여러 값을 시간차로 내보내기 위해
        yield StepEvent(
            step=step, name=name, status="done",
            duration_ms=duration_ms,
        )



_MISSING = object()


def _flatten(value, prefix: str = "") -> dict:
    """MasterSchema model_dump → {점표기 경로: 스칼라} 평탄화."""
    out: dict = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = value
    return out


def _delta_md(old_flat: dict, new_flat: dict) -> str:
    """직전 스냅샷 대비 추가/변경된 경로만 마크다운 불릿으로 — '그 단계가 채운 부분'."""
    lines: list[str] = []
    for path, new_val in new_flat.items():
        old_val = old_flat.get(path, _MISSING)
        if old_val is _MISSING:
            lines.append(f"- **{path}**: {new_val}")
        elif old_val != new_val:
            lines.append(f"- **{path}**: {old_val} → {new_val}")
    return "\n".join(lines) if lines else "_(변경 없음)_"


def _format_step5_detail(ms: MasterSchema) -> str:
    """5단계(KOSIS 셀 조회) 디버깅 상세 — 실제 데이터 그대로 표시.

    claim 추출값(원문 그대로, 띄어쓰기 포함) / KOSIS 에 넣은 값 / 후보 표별 항목·분류축·
    매칭 사유(왜 못 찾았는지) / 목표 셀 좌표 / 얻어낸 cell 값.
    master_schema(claims·analysis.cell_attempts·kosis_query·evidence)만으로 구성한다.
    """
    claims = {c.claim_id: c for c in ms.claims}
    out: list[str] = ["", "### 📊 5단계 상세 — claim 추출값 · 검색값 · 후보 표 디버깅", ""]
    for a in ms.analysis:
        c = claims.get(a.claim_id)
        if c is None:
            continue
        ev = a.evidence
        matched = ev is not None and ev.value is not None

        out.append(f"**[{a.claim_id}] {c.subject}**")
        # ① claim 추출값 — 추출된 그대로(띄어쓰기 포함). 값들은 | 로 구분
        out.append(
            f"- 📌 claim 추출값: "
            f"값 `{c.value.llm_value}`(원문 `{c.value.raw}`) "
            f"| 시점 `{c.period_value.llm_value}`(원문 `{c.period_value.raw}`) "
            f"| 모집단 `{c.population}` | 단위 `{c.unit}` | subject `{c.subject}`"
        )
        # ② KOSIS 에 실제로 넣은 값 (검색어는 공백 제거 형태)
        out.append(
            f"- 🔍 KOSIS 에 넣은 값: subject `{''.join(c.subject.split())}`(공백 제거) "
            f"| population `{c.population}` | period `{c.period_value.llm_value}`"
        )
        # ③ 후보 표별 조회 시도 — 항목·분류축·매칭 사유(왜 못 찾았는지)
        out.append(f"- 📑 후보 표별 조회 시도 {len(a.cell_attempts)}개:")
        for att in a.cell_attempts:
            star = " ★채택" if att.matched else ""
            out.append(f"    - `{att.tbl_id}` {att.tbl_nm}{star}")
            if att.error and att.error.startswith("스킵"):
                out.append(f"        - {att.error}")
                continue
            if att.items:
                out.append(f"        - 항목: {', '.join(att.items)}")
            for ax, vals in att.axes.items():
                out.append(f"        - 분류축 [{ax}]: {', '.join(vals)}")
            if att.matched:
                out.append(f"        - 결과: ✅ {att.value} {att.unit} (itmId {att.itm_id})")
            else:
                out.append(f"        - 결과: ❌ {att.error}")
        # ④ 목표 셀 좌표(찾으려는 것) + 얻어낸 값
        if matched:
            if a.kosis_query and a.kosis_query.params:
                out.append(f"- 🎯 얻으려는 셀 좌표: `{a.kosis_query.params}`")
            out.append(
                f"- 🎯 얻어낸 cell 값: **{ev.value} {ev.unit}** | 시점 {ev.period} "
                f"| 표 `{ev.kosis_tbl_id}` | itmId {ev.kosis_item_id}"
            )
        else:
            err = a.kosis_query.error_msg if a.kosis_query else "(조회 안 됨)"
            out.append(f"- 🎯 얻어낸 cell 값: ❌ 없음 — {err}")
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    async def _main() -> None:
        no_content = "기사가 없습니다."
        sample_content = "통계청에 따르면 지난달 한국 근로자의 주당 평균 근로시간은 38.8시간이다. 맥킨지는 노동시장 참여율을 높이는 것도 방법이라고 했다. 이 중 고령 인구가 노동시장에 남는 비율, 즉 ‘근로 수명’을 높이는 것도 고려해야 한다는 것이다. 일본의 경우 65세 이상 노동시장 참여율(26%)이 프랑스(4%) 등을 앞서고 있으며, 이는 일본의 1997년 이후 연평균 노동생산성 증가율(1.1%)이 서유럽(0.8%)을 앞설 수 있던 요인이 됐다고 했다. 하지만 맥킨지는 일본 방식도 한계는 있다고 봤다. 일본의 경우 25~64세는 주당 평균 30시간을 일하지만, 65세 이상은 7시간 일하는 것으로 집계돼 결국 고령화에 따른 노동시간 감소는 피할 수 없기 때문이다."

        content = sys.argv[1] if len(sys.argv) > 1 else sample_content
        result_path = Path(__file__).resolve().parents[2] / "tests" / "result.md"
        result_path.write_text("# 단계별 기록 (각 단계가 채운 부분)\n", encoding="utf-8")

        # 시작 스냅샷(전부 비어 있음) 기준으로 단계별 델타만 기록한다.
        prev = _flatten(MasterSchema(content=content).model_dump(by_alias=False))

        def record(step: int, name: str, ms: MasterSchema) -> None:
            nonlocal prev
            curr = _flatten(ms.model_dump(by_alias=False))
            section = f"\n## {step}. {name}\n\n{_delta_md(prev, curr)}\n"
            if step == 5:  # 5단계는 사람이 보기 좋은 요약을 하단에 덧붙인다
                section += _format_step5_detail(ms) + "\n"
            with result_path.open("a", encoding="utf-8") as f:
                f.write(section)
            prev = curr

        async for ev in Pipeline().run(content, on_step=record):
            print(ev)
        print(f"[result.md 저장] {result_path}")

    asyncio.run(_main())