"""KOSIS 메타데이터 검증기 — 응답 '구조'가 메타와 맞는지 검사.

[왜 '값 유무'로 검증하지 않는가]
처음엔 좌표로 셀을 조회해 값이 오면 OK로 봤다. 틀린 기준이다.
error 30 은 '값이 없다'는 뜻이지 '코드가 틀렸다'가 아니다. (empty ≠ invalid)

첫 검증에서 7표가 FAIL 났다. 원인은 전부 빈 셀이었다.
검증기가 자동으로 고른 셀(첫 분류값 + 최신 시점)이 비었을 뿐이다.
시점을 과거로 바꾸니 같은 코드로 값이 나왔다. 메타는 멀쩡했다.
즉 '값 유무'는 정당한 빈 셀에 속아 거짓 실패를 낸다.

[무엇으로 검증하는가]
값 유무가 아니라 응답의 *구조*가 메타와 맞는지 본다.
안전한 시점에서 objL=ALL 로 한 번 조회한 뒤 4가지를 본다.

  [A] 파싱 완전성 (데이터 호출 불필요)
      원시 getMeta(ITM) 행 수 == len(items) + Σ len(axis.values). 흘린 행 0.
      파서가 메타 응답을 빠짐없이 담았는지 본다.

  [B] 축 개수 일치
      응답의 C\\d+ 열 수 == schema.axis_count. (응답 C열이 진짜 축 수의 oracle)

  [C] 역방향 코드 대조 (응답 ⊆ 메타)
      응답에 나온 모든 C{n} 코드가 메타 axes[n-1] 값에 있어야 한다.
      응답에만 있고 메타에 없으면 = 메타가 코드를 누락 → 결함.
      (반대 방향은 전수 풀 없이는 못 봐서 검증 범위 밖.)

  [D] 라벨 정합성
      응답 C{n}_NM == 메타 축값 이름. 코드와 라벨이 엇갈리지 않았는지 본다.

[안전한 시점 선택]
END_PRD_DE 는 수록 끝일 뿐, 모든 셀이 찬 건 아니다. (추계는 미래)
그래서 [START, 2015 앵커, END] 순으로 시도해 행이 오는 첫 시점을 쓴다.
START 는 첫 수록점이라 안전하다. 2015 앵커는 START 가 늦은 표를 보완한다.

[판정 규칙]
  FAIL         : [A] 파싱 불완전 / error 20·21(objL 구조 오류) /
                 [B] 축 수 불일치 / [C] 메타 누락 코드 / [D] 라벨 불일치
  INCONCLUSIVE : 모든 후보 시점에서 error 30·행 0 (구조 검증 불가, 메타 결함 아님)
  PASS         : 위 결함 없음

한계: [C] 는 '응답에 나온 코드'만 보는 부분 검증이다.
메타 전체를 보려면 전수 풀이 필요하다. 비싸고 모호해 범위 밖이다.
이 검증기는 '구조 정합'은 보장하되 '값 전수 완전'은 아니다.

실행:
    uv run x python tests/validate_meta.py        # 표별 상세 + JSON 저장
    uv run x pytest tests/validate_meta.py -v      # FAIL 0 단언

작성: leeaain2027, 2026-06-09
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import pytest

from src.kosis import (
    KosisError,
    KosisQuery,
    build_params,
    call_kosis,
    fetch_meta_item,
    fetch_table_schema,
    resolve_api_key,
)

OUT_PATH = Path(__file__).parent / "meta_validation_results.json"
_C_COL = re.compile(r"^C\d+$")
_REPORT_CAP = 8  # 보고 시 코드/불일치 목록 상한

# 검증 대상 30표 (collect_meta_testset.py, 2026-06-09)
META_TEST_TABLES: list[tuple[str, str, str]] = [
    ("101", "DT_1DA7104S", "행정구역(시도)/성별 실업률"),
    ("101", "DT_1DA7107S", "행정구역(시도)/연령별 실업률"),
    ("101", "DT_1DA7102S", "성/연령별 실업률"),
    ("101", "DT_1DA7001S", "성별 경제활동인구 총괄"),
    ("101", "DT_1DA7004S", "행정구역(시도)별 경제활동인구"),
    ("101", "DT_1DA7002S", "연령별 경제활동인구 총괄"),
    ("101", "DT_XNN0004", "합계출산율 - 동북·중앙아시아"),
    ("101", "DT_2KAA207", "합계출산율"),
    ("101", "DT_XNS0004", "합계출산율 - 남부·동남아시아"),
    ("101", "DT_1B83A11", "시도/부부의 혼인종류별 혼인"),
    ("101", "DT_1B8000H", "시도/인구동태건수 및 동태율"),
    ("101", "DT_1B83A24", "시도/시군구별 외국인과의 혼인"),
    ("101", "DT_1B85030", "이혼종류별 외국인과의 이혼"),
    ("101", "DT_1B85026", "미성년자녀수/외국인 남편의 국적별 이혼"),
    ("101", "DT_1B85019", "연령(5세)/이혼종류별 이혼"),
    ("101", "DT_2IFS002", "소비자물가지수"),
    ("101", "DT_2OEEO0121", "소비자물가지수"),
    ("101", "DT_1J22003", "소비자물가지수(2020=100)"),
    ("101", "DT_2KAA202", "부양비 및 노령화지수"),
    ("101", "DT_XNS0011", "부양인구비 및 노령화지수 - 남부·동남아시아"),
    ("101", "DT_XNN0011", "부양인구비 및 노령화지수 - 동북·중앙아시아"),
    ("101", "DT_1B34E07", "사망원인/성/연령별 사망자수, 사망률"),
    ("101", "DT_1B34E18", "특정 사망원인(고의적 자해)(분기별)"),
    ("101", "DT_1B34E19", "시도별 특정 사망원인(고의적 자해)(분기별)"),
    ("101", "DT_1B8000I", "시군구/인구동태건수 및 동태율"),
    ("101", "DT_2UNS0237", "5세 미만 출생 등록 비율"),
    ("101", "DT_XNS0110", "경제성장률(불변가격) - 남부·동남아시아"),
    ("388", "TX_38803_A026", "연도별 전력수급 실적"),
    ("101", "DT_1YL20571", "경제성장률(시도)"),
    ("360", "DT_36005_A003", "항목별 EBSI"),
]

# se_code → 데이터 보장이 비교적 확실한 고정 앵커(START 가 늦은 표 보완용)
_ANCHOR = {"Y": "2015", "M": "201501", "Q": "201501", "H": "201501", "D": "20150101"}


def _norm(s) -> str:
    return "".join(str(s or "").split())


def _orig_to_req(orig: str, se_code: str | None) -> str | None:
    """PRD 메타 원본 표기 → 요청 시점 형식. 모르면 None.

    Y '2025'→'2025'  M '2026.04'→'202604'  Q/H '2026 1/4'→'202601'  D 숫자8자리.
    """
    s = (orig or "").strip()
    if not s or not se_code:
        return None
    if se_code == "Y":
        m = re.search(r"\d{4}", s)
        return m.group(0) if m else None
    if se_code == "M":
        d = re.sub(r"\D", "", s)
        return d[:6] if len(d) >= 6 else None
    if se_code == "D":
        d = re.sub(r"\D", "", s)
        return d[:8] if len(d) >= 8 else None
    if se_code in ("Q", "H"):
        m = re.match(r"(\d{4})\D+(\d+)\s*/", s)
        if m:
            return f"{m.group(1)}{int(m.group(2)):02d}"
        d = re.sub(r"\D", "", s)
        return d[:6] if len(d) >= 6 else None
    return None


def _is_obj_error(msg: str) -> bool:
    """error 20(필수변수 누락)/21(잘못된 요청 변수) — objL 구조 오류."""
    return msg.startswith("20:") or msg.startswith("21:")


def _is_no_data(msg: str) -> bool:
    """error 30 — 데이터 없음(코드 무효 증거 아님)."""
    return msg.startswith("30:")


def _safe_periods(schema) -> tuple[str | None, list[str]]:
    """검증에 쓸 (prdSe, 후보 시점 목록). 데이터 보장 순으로 START→앵커→END."""
    for p in schema.periods:
        if not p.se_code:
            continue
        cands: list[str] = []
        for raw in (p.start, _ANCHOR.get(p.se_code), p.end):
            req = raw if (raw and raw == _ANCHOR.get(p.se_code)) else _orig_to_req(raw, p.se_code)
            if req and req not in cands:
                cands.append(req)
        if cands:
            return p.se_code, cands
    return None, []


def _check_parse(schema, raw_itm) -> dict:
    """[A] 파싱 완전성: 원시 ITM 행을 schema 가 빠짐없이 담았나(데이터 불필요)."""
    rows = [r for r in raw_itm if isinstance(r, dict)]
    item_rows = [r for r in rows if r.get("OBJ_ID") == "ITEM"]
    axis_rows = [r for r in rows if r.get("OBJ_ID") and r.get("OBJ_ID") != "ITEM"]
    dropped = [r for r in rows if not r.get("OBJ_ID")]
    parsed_axis_vals = sum(len(a.values) for a in schema.axes)
    ok = (len(schema.items) == len(item_rows)
          and parsed_axis_vals == len(axis_rows)
          and not dropped)
    return {
        "raw_dict_rows": len(rows),
        "parsed_items": len(schema.items), "raw_item_rows": len(item_rows),
        "parsed_axis_vals": parsed_axis_vals, "raw_axis_rows": len(axis_rows),
        "dropped_rows": len(dropped),
        "ok": ok,
    }


def _query_all(schema, se: str, period: str) -> list[dict]:
    """objL=ALL 로 한 시점 조회 → 응답 rows. 호출 오류는 그대로 raise."""
    n = schema.axis_count
    q = KosisQuery(
        org_id=schema.org_id, tbl_id=schema.tbl_id,
        itm_id=schema.items[0].itm_id, period=period, period_se=se,
        obj_l1="ALL",
        obj_l2="ALL" if n >= 2 else "",
        obj_l3="ALL" if n >= 3 else "",
        obj_l4="ALL" if n >= 4 else "",
    )
    return [r for r in call_kosis(build_params(q, _KEY)) if isinstance(r, dict)]


def _check_response(schema) -> dict:
    """[B][C][D] 응답 구조 정합성: 축 수·역방향 코드·라벨 대조."""
    d: dict = {"ok": False, "status": None, "period_used": None}
    if not schema.items:
        d["status"] = "skip:항목없음"
        return d
    if schema.axis_count > 4:
        d["status"] = f"skip:축{schema.axis_count}개(>4 미지원)"
        return d

    se, cands = _safe_periods(schema)
    if not cands:
        d["status"] = "skip:유효주기없음"
        return d

    rows: list[dict] = []
    last_err = None
    for prd in cands:  # 행이 올 때까지 안전 시점 순회
        try:
            rows = _query_all(schema, se, prd)
        except KosisError as e:
            last_err = str(e)
            if _is_obj_error(last_err):  # objL 구조 오류는 즉시 결함
                d["status"] = f"objL오류:{last_err}"
                return d
            continue  # error 30 등은 다음 후보 시점으로
        if rows:
            d["period_used"] = prd
            break

    if not rows:
        d["status"] = f"inconclusive:데이터없음({last_err or '행0'})"
        return d

    # [B] 축 개수
    c_cols = sorted({k for r in rows for k in r if _C_COL.match(k)})
    d["axis_cols"] = c_cols
    d["axis_count_match"] = len(c_cols) == schema.axis_count

    # [C][D] 역방향 코드 + 라벨 (C{i} ↔ axes[i-1], OBJ_ID_SN 순)
    unknown: dict[str, list[str]] = {}
    label_mism: list[dict] = []
    for i, ax in enumerate(schema.axes[: len(c_cols)], start=1):
        col = f"C{i}"
        meta_nm = {code: nm for code, nm in ax.values}
        seen_codes, seen_mism = set(), set()
        for r in rows:
            code = r.get(col)
            if code is None or code in seen_codes:
                continue
            seen_codes.add(code)
            if code not in meta_nm:
                unknown.setdefault(col, []).append(code)
            elif _norm(r.get(f"{col}_NM")) != _norm(meta_nm[code]) and code not in seen_mism:
                seen_mism.add(code)
                label_mism.append({"col": col, "code": code,
                                   "meta": meta_nm[code], "resp": r.get(f"{col}_NM")})
    d["unknown_codes"] = {k: v[:_REPORT_CAP] for k, v in unknown.items()}
    d["label_mismatch"] = label_mism[:_REPORT_CAP]
    d["rows_returned"] = len(rows)
    d["ok"] = (d["axis_count_match"] and not unknown and not label_mism)
    d["status"] = "ok" if d["ok"] else "mismatch"
    return d


def _verdict(parse: dict, resp: dict, schema) -> tuple[str, list[str]]:
    notes: list[str] = []
    fail = False

    if not parse["ok"]:
        fail = True
        notes.append(f"[A] 파싱 불완전(흘린 행 {parse['dropped_rows']}, "
                     f"항목 {parse['parsed_items']}/{parse['raw_item_rows']}, "
                     f"축값 {parse['parsed_axis_vals']}/{parse['raw_axis_rows']})")

    st = resp.get("status") or ""
    if st.startswith("skip"):
        notes.append(f"[B-D] {st}")
    elif st.startswith("inconclusive"):
        notes.append(f"[B-D] {st}")
        return ("INCONCLUSIVE" if not fail else "FAIL"), notes
    elif st.startswith("objL오류"):
        fail = True
        notes.append(f"[B] {st}")
    else:
        if not resp.get("axis_count_match"):
            fail = True
            notes.append(f"[B] 축 수 불일치(메타 {schema.axis_count} vs 응답 "
                         f"{len(resp.get('axis_cols', []))})")
        if resp.get("unknown_codes"):
            fail = True
            notes.append(f"[C] 메타 누락 코드(응답엔 있음): {resp['unknown_codes']}")
        if resp.get("label_mismatch"):
            fail = True
            notes.append(f"[D] 라벨 불일치: {resp['label_mismatch']}")

    if not schema.periods:
        notes.append("주기 0개(PRD 실패 의심)")
    none_se = [p.se_label for p in schema.periods if p.se_code is None]
    if none_se:
        notes.append(f"se_code 매핑 누락: {none_se}")

    if fail:
        return "FAIL", notes
    return ("PASS", notes) if st == "ok" else ("INCONCLUSIVE", notes)


async def _validate(org: str, tbl: str, name: str) -> dict:
    rec: dict = {"org_id": org, "tbl_id": tbl, "name": name}
    try:
        schema = await fetch_table_schema(org, tbl, _KEY)
        raw_itm = await asyncio.to_thread(fetch_meta_item, org, tbl, "ITM", _KEY)
    except Exception as exc:  # noqa: BLE001
        rec.update(verdict="FAIL", notes=[f"메타 조회 실패: {type(exc).__name__}: {exc}"])
        return rec
    parse = _check_parse(schema, raw_itm)
    resp = await asyncio.to_thread(_check_response, schema)
    verdict, notes = _verdict(parse, resp, schema)
    rec.update(
        verdict=verdict, notes=notes, parse=parse, response=resp,
        item_count=len(schema.items), axis_count=schema.axis_count,
        period_count=len(schema.periods),
    )
    return rec


_KEY = ""  # _run_all 에서 1회 주입(스레드 위임 함수가 공유)


async def _run_all() -> list[dict]:
    global _KEY
    _KEY = resolve_api_key()
    return await asyncio.gather(
        *(_validate(o, t, n) for o, t, n in META_TEST_TABLES)
    )


# ── pytest ───────────────────────────────────────────────────────────────────
live = pytest.mark.skipif(
    not os.getenv("KOSIS_API_KEY"),
    reason="KOSIS_API_KEY 없음 — live 메타 검증 skip (uv run x 로 실행)",
)


@live
def test_no_structural_mismatch():
    """30표 메타가 응답 구조와 정합(파싱 완전·축 수·코드·라벨). FAIL 0 단언."""
    results = asyncio.run(_run_all())
    fails = [(r["tbl_id"], r["notes"]) for r in results if r["verdict"] == "FAIL"]
    assert not fails, f"구조 불일치 {len(fails)}건: {fails}"


# ── 단독 실행(상세 출력 + JSON 저장) ──────────────────────────────────────────
def main() -> None:
    records = asyncio.run(_run_all())
    by = {"PASS": [], "INCONCLUSIVE": [], "FAIL": []}
    for r in records:
        by.setdefault(r["verdict"], []).append(r)

    payload = {
        "summary": {
            "total": len(records),
            "PASS": len(by["PASS"]),
            "INCONCLUSIVE": len(by["INCONCLUSIVE"]),
            "FAIL": len(by["FAIL"]),
        },
        "results": records,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"총 {len(records)}표  PASS {len(by['PASS'])}  "
          f"INCONCLUSIVE {len(by['INCONCLUSIVE'])}  FAIL {len(by['FAIL'])}\n")
    icon = {"PASS": "✓", "INCONCLUSIVE": "?", "FAIL": "✗"}
    for r in records:
        rp = r.get("response", {})
        print(f"{icon.get(r['verdict'],'·')} {r['org_id']}/{r['tbl_id']}  "
              f"항목{r.get('item_count','?')}·축{r.get('axis_count','?')}·"
              f"주기{r.get('period_count','?')}  "
              f"시점={rp.get('period_used','-')}  | {r['name']}")
        for n in r.get("notes", []):
            print(f"      - {n}")
    print(f"\n저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
