"""KOSIS 3단계만 테스트 — 통계표 조회 → 메타 조회 → 값 조회.

runner.py 의 [4] retrieve_kosis_candidates(통계표 조회)와 [5] fetch_kosis_data(메타+값 조회)만 떼어 낸다.
claim 하나로 실제 배선대로 돌려 본다.

  [4] retrieve_kosis_candidates : search_tables        → analysis[].candidates
  [5] fetch_kosis_data          : resolve(getMeta)     → analysis[].cell_attempts (메타 trace)
                                  fetch_cell_with_retry → analysis[].evidence (선정 셀 값)

예시 claim: '2023년 청년 고용률'
  subject='고용률'(→ itmId), population='청년'(→ 분류축 값), period=2023(Y)

이 claim 은 '청년'이 표의 연령축 값('15~29세' 등)과 이름매칭이 안 된다.
(resolve.py 의 결정적 매칭 한계, case C)
그래서 좌표 해소가 실패할 수 있다. 그 과정을 그대로 관찰한다.

    uv run x python tests/test_kosis_three_stages.py
    uv run x pytest tests/test_kosis_three_stages.py -v
"""
from __future__ import annotations

import asyncio
import os

import pytest
from dotenv import load_dotenv

from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import Claim, ClaimType, MasterSchema, ValueSlot

load_dotenv()  # KOSIS_API_KEY 는 infisical 아닌 .env 에서 옴 (resolve_api_key 와 동일)


def _slot(raw: str, val: str) -> ValueSlot:
    return ValueSlot(raw=raw, llm_value=val, is_inferred=False)


def _make_claim() -> Claim:
    """'2023년 청년 고용률' → subject=고용률, population=청년, period=2023(Y)."""
    return Claim(
        claim_id="c1",
        article_id="a1",
        sentence="2023년 청년 고용률은 46.5%였다.",
        claim_type=ClaimType.ABSOLUTE,
        subject="고용률",
        value=_slot("46.5%", "46.5"),
        unit="%",
        aggregation="",
        period_type="Y",
        period_value=_slot("2023년", "2023"),
        population="청년",
        cited_source="통계청",
    )


async def run_three_stages(claim: Claim) -> MasterSchema:
    """[4]→[5] 두 단계를 실제 배선대로 실행하고 채워진 MasterSchema 반환."""
    ms = MasterSchema(content="(테스트)")
    ms.claims = [claim]
    await retrieve_kosis_candidates(ms)   # [4] 통계표 조회
    await fetch_kosis_data(ms)            # [5] 메타 조회 + 값 조회
    return ms


def _print_report(ms: MasterSchema) -> None:
    an = ms.analysis[0]
    print("\n=== [4] 통계표 조회 (retrieve_kosis_candidates) ===")
    s = an.kosis_search
    print(f"  검색어='{s.query}'  hits={s.hits}  선정={s.selected_tbl_id} ({s.selected_tbl_name})")
    for i, c in enumerate(an.candidates, 1):
        print(f"    {i}. {c.org_id}/{c.tbl_id}  {c.tbl_nm}")

    print("\n=== [5] 메타 조회 + 값 조회 (fetch_kosis_data) ===")
    print(f"  kosis_query: success={an.kosis_query.success}  error={an.kosis_query.error_msg}")
    print(f"  cell_attempts ({len(an.cell_attempts)}표):")
    for a in an.cell_attempts:
        head = "✓매칭" if a.matched else "✗"
        print(f"    {head} {a.tbl_id}  itm_id={a.itm_id}")
        if a.axes:
            for ax, vals in a.axes.items():
                print(f"        축 '{ax}': {vals[:8]}")
        if a.matched:
            print(f"        → 값 {a.value} {a.unit}")
        elif a.error:
            print(f"        → {a.error}")

    print("\n=== 최종 evidence ===")
    ev = an.evidence
    if ev is None:
        print("  evidence=None (좌표 해소/조회 실패 — 위 사유 참조)")
    else:
        print(f"  값={ev.value} {ev.unit}  표={ev.kosis_tbl_id}({ev.table_name})")
        print(f"  itmId={ev.kosis_item_id}  classification(match_filters)={ev.classification}")


# ── pytest ───────────────────────────────────────────────────────────────────
live = pytest.mark.skipif(
    not os.getenv("KOSIS_API_KEY"),
    reason="KOSIS_API_KEY 없음 — live 3단계 테스트 skip (uv run x 로 실행)",
)


@live
def test_three_stages_run_without_crash():
    """3단계가 예외 없이 끝나고 analysis/candidates 를 채운다(좌표 해소 성패와 무관)."""
    ms = asyncio.run(run_three_stages(_make_claim()))
    assert len(ms.analysis) == 1
    an = ms.analysis[0]
    assert an.kosis_search.hits > 0, "통계표 검색 0건"
    assert an.candidates, "후보 표 0건"
    # evidence 는 있을 수도(매칭 성공) 없을 수도(청년↔연령대 매칭 실패) 있다.
    # 어느 쪽이든 cell_attempts 에 표별 시도 기록이 남아야 한다.
    assert an.cell_attempts, "셀 조회 시도 기록 없음"


if __name__ == "__main__":
    if not os.getenv("KOSIS_API_KEY"):
        raise SystemExit("KOSIS_API_KEY 없음 — uv run x python tests/test_kosis_three_stages.py")
    ms = asyncio.run(run_three_stages(_make_claim()))
    _print_report(ms)
