"""KOSIS 기간 유형(Y/M/Q/S) 실제 호출 테스트.

스키마 변경 검증(오프라인) + KOSIS API 실제 호출(온라인) 을 함께 실행한다.

실행:
    python test_kosis_period_types.py
"""
from __future__ import annotations

import sys
import traceback

# ── 1. 스키마 변경 검증 (오프라인) ───────────────────────────────────────────

def test_schema():
    print("=" * 60)
    print("[1] 스키마 변경 검증 (오프라인)")
    print("=" * 60)

    # PeriodType Literal 에 "S" 포함 확인
    from src.schemas.runtime import PeriodType
    import typing
    args = typing.get_args(PeriodType)
    assert "S" in args, f"PeriodType 에 'S' 없음: {args}"
    print(f"  PeriodType args : {args}  ✓")

    # Claim / Evidence period_type="S" Pydantic 검증 통과 확인
    from src.schemas.runtime import Claim, Evidence, ValueSlot
    from src.schemas.runtime import ClaimType
    c = Claim(
        claim_id="test-s-001",
        article_id="art-001",
        sentence="2024년 상반기 수출액은 3억 달러였다.",
        claim_type=ClaimType.ABSOLUTE,
        subject="수출액",
        value=ValueSlot(raw="3억", llm_value="300000000", is_inferred=False),
        unit="달러",
        aggregation="값",
        period_type="S",
        period_value=ValueSlot(raw="2024년 상반기", llm_value="2024-H1", is_inferred=False),
        population="전체",
        cited_source="관세청",
    )
    assert c.period_type == "S"
    print(f"  Claim(period_type='S') 생성  ✓")

    e = Evidence(
        claim_id="test-s-001",
        source="KOSIS",
        subject="수출액",
        unit="달러",
        period_type="S",
        period="202401",
        population="전체",
    )
    assert e.period_type == "S"
    print(f"  Evidence(period_type='S') 생성  ✓")

    # _VALID_PERIOD_TYPES 에 "S" 포함 확인
    from src.modules.extract_statistical_claims import _VALID_PERIOD_TYPES
    assert "S" in _VALID_PERIOD_TYPES, f"_VALID_PERIOD_TYPES 에 'S' 없음: {_VALID_PERIOD_TYPES}"
    print(f"  _VALID_PERIOD_TYPES : {sorted(_VALID_PERIOD_TYPES)}  ✓")

    print()


def test_format_period():
    print("=" * 60)
    print("[2] _format_period 동작 검증 (오프라인)")
    print("=" * 60)

    from src.modules.generate_explanation import _format_period

    cases = [
        # (period_type, period, expected_contains)
        # 정규화 형식
        ("Y",  "2024",      "2024년"),
        ("M",  "2024-01",   "2024년 1월"),
        ("Q",  "2024-Q3",   "2024년 3분기"),
        ("S",  "2024-H1",   "2024년 상반기"),
        ("S",  "2024-H2",   "2024년 하반기"),
        # KOSIS PRD_DE 형식
        ("M",  "202403",    "2024년 3월"),
        ("Q",  "202402",    "2024년 2분기"),
        ("S",  "202401",    "상반기"),
        ("S",  "202402",    "하반기"),
        ("D",  "20240315",  "2024년 3월 15일"),
    ]

    ok = True
    for pt, p, expected in cases:
        result = _format_period(pt, p)
        passed = expected in result
        mark = "✓" if passed else "✗"
        print(f"  {mark}  _format_period({pt!r}, {p!r}) = {result!r}  (기대: {expected!r} 포함)")
        if not passed:
            ok = False

    assert ok, "일부 _format_period 케이스 실패"
    print()


def test_to_kosis_period():
    print("=" * 60)
    print("[3] _to_kosis_period 변환 검증 (오프라인)")
    print("=" * 60)

    from src.modules.fetch_kosis_data import _to_kosis_period

    cases = [
        ("Y", "2024",    "2024"),
        ("Y", "2023년",  "2023"),
        ("M", "2024-01", "202401"),
        ("M", "2024-12", "202412"),
        ("Q", "2024-Q1", "202401"),
        ("Q", "2024-Q4", "202404"),
        ("S", "2024-H1", "202401"),
        ("S", "2024-H2", "202402"),
    ]

    ok = True
    for pt, raw, expected in cases:
        result = _to_kosis_period(pt, raw)
        passed = result == expected
        mark = "✓" if passed else "✗"
        print(f"  {mark}  _to_kosis_period({pt!r}, {raw!r}) = {result!r}  (기대: {expected!r})")
        if not passed:
            ok = False

    assert ok, "일부 _to_kosis_period 케이스 실패"
    print()


def _probe(label, q, api_key):
    """KosisQuery 로 rows 를 직접 받아 첫 번째 셀 정보를 출력한다."""
    from src.kosis.cell import build_params
    from src.kosis.client import call_kosis
    rows = call_kosis(build_params(q, api_key))
    if rows and isinstance(rows, list) and isinstance(rows[0], dict):
        s = rows[0]
        print(f"      {label}: rows={len(rows)}건  PRD_SE={s.get('PRD_SE')}  PRD_DE={s.get('PRD_DE')}  DT={s.get('DT')}  UNIT={s.get('UNIT_NM')}  OK")
        return rows
    else:
        print(f"      {label}: 응답 없음 (rows={rows!r})")
        return []


def test_live_kosis():
    print("=" * 60)
    print("[4] KOSIS 실제 API 호출 (온라인)")
    print("=" * 60)

    from src.kosis import resolve_api_key, search_tables
    from src.kosis.cell import KosisQuery

    try:
        api_key = resolve_api_key()
    except Exception as e:
        print(f"  API 키 없음 -- 온라인 테스트 건너뜀: {e}")
        return

    # ── (a) 연간(Y): 경제활동인구 연간 검색 ──────────────────────────────────
    print("\n  [Y] 경제활동인구 연간 -- 상위 3개 표 목록")
    try:
        hits = search_tables("경제활동인구", api_key, top_n=3)
        for h in hits:
            print(f"      [{h.org_id}/{h.tbl_id}] {h.tbl_nm}  {h.prd_de}")
    except Exception as e:
        print(f"      검색 실패: {e}")

    # ── (b) 월간(M): 소비자물가지수 -- itmId 메타 조회 후 probe ────────────
    print("\n  [M] 소비자물가지수 월별 -- 메타 itmId 조회 후 2024년 1월 probe")
    try:
        from src.kosis import fetch_meta_item
        hits = search_tables("소비자물가지수", api_key, top_n=3)
        for h in hits:
            print(f"      [{h.org_id}/{h.tbl_id}] {h.tbl_nm}  {h.prd_de}")
        if hits:
            h = hits[0]
            itm_rows = fetch_meta_item(h.org_id, h.tbl_id, "ITM", api_key)
            item_rows = [r for r in itm_rows if isinstance(r, dict) and r.get("OBJ_ID") == "ITEM"]
            print(f"      ITEM 수={len(item_rows)}")
            if item_rows:
                itm_id = item_rows[0]["ITM_ID"]
                itm_nm = item_rows[0].get("ITM_NM", "")
                print(f"      첫 itmId={itm_id!r}  name={itm_nm!r}")
                q = KosisQuery(
                    org_id=h.org_id, tbl_id=h.tbl_id,
                    itm_id=itm_id, obj_l1="ALL", obj_l2="ALL",
                    period="202401", period_se="M",
                )
                rows = _probe("M probe", q, api_key)
                if rows:
                    prds = sorted({r.get("PRD_DE") for r in rows if isinstance(r, dict) and r.get("PRD_DE")})
                    print(f"        PRD_DE 목록(최대 5): {prds[:5]}")
    except Exception as e:
        print(f"      월간 테스트 실패: {e}")

    # ── (c) 분기(Q): GDP 분기 -- 메타데이터로 itmId 조회 후 probe ──────────
    print("\n  [Q] 국내총생산 분기 -- 메타 itmId 조회 후 2024년 1분기 probe")
    try:
        from src.kosis import fetch_meta_item
        hits = search_tables("국내총생산", api_key, top_n=5)
        q_hits = [h for h in hits if "분기" in h.tbl_nm]
        for h in (q_hits or hits)[:3]:
            print(f"      [{h.org_id}/{h.tbl_id}] {h.tbl_nm}  {h.prd_de}")
        h = (q_hits or hits)[0]
        itm_rows = fetch_meta_item(h.org_id, h.tbl_id, "ITM", api_key)
        item_rows = [r for r in itm_rows if isinstance(r, dict) and r.get("OBJ_ID") == "ITEM"]
        print(f"      ITEM 수={len(item_rows)}")
        if item_rows:
            itm_id = item_rows[0]["ITM_ID"]
            itm_nm = item_rows[0].get("ITM_NM", "")
            print(f"      첫 itmId={itm_id!r}  name={itm_nm!r}")
            q = KosisQuery(
                org_id=h.org_id, tbl_id=h.tbl_id,
                itm_id=itm_id, obj_l1="ALL", obj_l2="ALL",
                period="202401", period_se="Q",
            )
            rows = _probe("Q probe", q, api_key)
            if rows:
                prds = sorted({r.get("PRD_DE") for r in rows if isinstance(r, dict) and r.get("PRD_DE")})
                print(f"        PRD_DE 목록(최대 5): {prds[:5]}")
    except Exception as e:
        print(f"      분기 테스트 실패: {e}")

    # ── (d) 반기(S): 근로장려금 반기 -- 메타 itmId 조회 후 probe ───────────
    print("\n  [S] 근로장려금 반기 지급현황 -- 메타 itmId 조회 후 probe")
    try:
        from src.kosis import fetch_meta_item
        s_cands = [
            ("133", "DT_133001N_1451"),  # 반기별 근로장려금 지급 현황
            ("133", "DT_133001N_1452"),  # 소득종류별 반기
        ]
        found_s = False
        for org_id, tbl_id in s_cands:
            print(f"\n      표 [{org_id}/{tbl_id}] 메타 조회")
            try:
                itm_rows = fetch_meta_item(org_id, tbl_id, "ITM", api_key)
                item_rows = [r for r in itm_rows if isinstance(r, dict) and r.get("OBJ_ID") == "ITEM"]
                print(f"        ITEM 수={len(item_rows)}")
                for r in item_rows[:3]:
                    print(f"        itmId={r['ITM_ID']!r}  name={r.get('ITM_NM')!r}")
                if not item_rows:
                    continue
                itm_id = item_rows[0]["ITM_ID"]
                for period in ("202502", "202501", "202402", "202401"):
                    q = KosisQuery(
                        org_id=org_id, tbl_id=tbl_id,
                        itm_id=itm_id, obj_l1="ALL", obj_l2="ALL",
                        period=period, period_se="S",
                    )
                    try:
                        rows = _probe(f"S probe period={period}", q, api_key)
                        if rows:
                            prds = sorted({r.get("PRD_DE") for r in rows if isinstance(r, dict)})
                            print(f"          PRD_DE 전체: {prds}")
                            found_s = True
                            break
                    except Exception as e3:
                        print(f"          period={period} 실패: {e3}")
                if found_s:
                    break
            except Exception as e2:
                print(f"        메타 조회 실패: {e2}")
        if not found_s:
            print("      반기 표 응답 없음")
    except Exception as e:
        print(f"      반기 테스트 실패: {e}")

    print()


def main():
    failures = []

    for fn in [test_schema, test_format_period, test_to_kosis_period, test_live_kosis]:
        try:
            fn()
        except AssertionError as e:
            print(f"  FAIL: {e}\n")
            failures.append(fn.__name__)
        except Exception as e:
            print(f"  ERROR in {fn.__name__}: {e}")
            traceback.print_exc()
            failures.append(fn.__name__)

    print("=" * 60)
    if failures:
        print(f"실패: {failures}")
        sys.exit(1)
    else:
        print("전체 통과  ✓")


if __name__ == "__main__":
    main()
