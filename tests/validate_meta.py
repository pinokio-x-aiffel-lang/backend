"""메타데이터 내용 검증기 — 구조 완전성 + 데이터 API 교차검증.

30개 (org_id, tbl_id) 에 대해 두 층위로 검증한다.

[A] 파싱 완전성 (데이터 API 불필요, 순수 구조)
    원시 getMeta(ITM) 행 수 == len(items) + Σ len(axis.values).
    안 맞으면 파서가 행을 흘림(OBJ_ID 누락 등). dropped 로 보고.

[B] 소스 완전성 (데이터 API 교차검증)
    메타에서 뽑은 코드(itmId / objL / prdSe)로 statisticsParameterData 를 호출해:
      - 축 개수 : 응답 C\\d+ 열 수 == axis_count           (oracle 대조)
      - 코드 작동: 보낸 좌표가 정상 행 반환                  (코드 실재)
      - 라벨 정합: 응답 C{n}_NM == 메타 축 값 이름           (코드↔라벨)
    값 목록 전수(모든 코드)는 전수 풀이 필요해 검증 범위 밖 — 첫 값만 시험(표본).

판정: FAIL(구조 깨짐/호출 불가/축 수 불일치) > WARN(셀 0건·라벨 불일치·주기 이상) > PASS.

    uv run x python tests/validate_meta.py
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from src.kosis import (
    KosisError,
    KosisQuery,
    build_params,
    call_kosis,
    fetch_meta_item,
    fetch_table_schema,
    find_cell_row,
    resolve_api_key,
)

OUT_PATH = Path(__file__).parent / "meta_validation_results.json"
_C_COL = re.compile(r"^C\d+$")

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


def _norm(s) -> str:
    return "".join(str(s or "").split())


def _orig_to_req(end: str, se_code: str | None) -> str | None:
    """PRD 메타의 원본 표기(END_PRD_DE) → 요청 시점 형식. 모르면 None.

    Y '2025'→'2025'  M '2026.04'→'202604'  Q/H '2026 1/4'→'202601'  D 숫자8자리.
    """
    s = (end or "").strip()
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
    return msg.startswith("20:") or msg.startswith("21:")


def _call_capture(query: KosisQuery, key: str) -> list[dict]:
    """좌표로 데이터 호출, 응답 rows 반환. 다축 error 20/21 은 objL=ALL 사다리로 재시도."""
    try:
        return call_kosis(build_params(query, key))
    except KosisError as e:
        if not _is_obj_error(str(e)):
            raise
    import dataclasses
    ladders = [
        ("ALL", query.obj_l2, query.obj_l3, query.obj_l4),
        ("ALL", "ALL", query.obj_l3, query.obj_l4),
        ("ALL", "ALL", "ALL", query.obj_l4),
        ("ALL", "ALL", "ALL", "ALL"),
    ]
    last: Exception | None = None
    for l1, l2, l3, l4 in ladders:
        retry = dataclasses.replace(query, obj_l1=l1, obj_l2=l2, obj_l3=l3, obj_l4=l4)
        try:
            return call_kosis(build_params(retry, key))
        except KosisError as e:
            if not _is_obj_error(str(e)):
                raise
            last = e
    raise last if last else KosisError("objL 재시도 모두 실패")


def _check_parse(schema, raw_itm) -> dict:
    """[A] 파싱 완전성: 원시 ITM 행을 schema 가 빠짐없이 담았나."""
    rows = [r for r in raw_itm if isinstance(r, dict)]
    item_rows = [r for r in rows if r.get("OBJ_ID") == "ITEM"]
    axis_rows = [r for r in rows if r.get("OBJ_ID") and r.get("OBJ_ID") != "ITEM"]
    dropped = [r for r in rows if not r.get("OBJ_ID")]  # OBJ_ID 없는 행(두 파서 모두 무시)
    parsed_axis_vals = sum(len(a.values) for a in schema.axes)
    ok = (len(schema.items) == len(item_rows)
          and parsed_axis_vals == len(axis_rows)
          and not dropped)
    return {
        "raw_dict_rows": len(rows),
        "raw_item_rows": len(item_rows),
        "raw_axis_rows": len(axis_rows),
        "parsed_items": len(schema.items),
        "parsed_axis_vals": parsed_axis_vals,
        "dropped_rows": len(dropped),
        "ok": ok,
    }


def _check_data(schema, key: str) -> dict:
    """[B] 데이터 교차검증: 메타 코드로 셀 조회 → 축 수·작동·라벨 대조."""
    d: dict = {"ok": False, "error": None, "skipped": None}
    if not schema.items:
        d["skipped"] = "항목 없음 — 교차검증 불가"
        return d

    # 시점: se_code 있는 첫 주기의 END 를 요청 형식으로
    period = se = None
    for p in schema.periods:
        req = _orig_to_req(p.end, p.se_code)
        if req:
            period, se = req, p.se_code
            break
    if period is None:
        d["skipped"] = "유효 주기 없음 — 교차검증 불가"
        return d

    axes = schema.axes  # OBJ_ID_SN 순
    if len(axes) > 4:
        d["skipped"] = f"축 {len(axes)}개(>4) — KosisQuery 미지원"
        return d

    obj = ["", "", "", ""]
    match: dict[str, str] = {}
    expect_nm: dict[str, str] = {}
    for i, ax in enumerate(axes):
        code, nm = ax.values[0]
        obj[i] = code
        match[f"C{i+1}"] = code
        expect_nm[f"C{i+1}"] = nm

    query = KosisQuery(
        org_id=schema.org_id, tbl_id=schema.tbl_id, itm_id=schema.items[0].itm_id,
        period=period, period_se=se, match_filters=match,
        obj_l1=obj[0] or "ALL", obj_l2=obj[1], obj_l3=obj[2], obj_l4=obj[3],
    )
    d.update(period_used=period, prd_se_used=se, itm_id=schema.items[0].itm_id)

    try:
        rows = _call_capture(query, key)
    except (KosisError, ValueError) as exc:
        d["error"] = f"{type(exc).__name__}: {exc}"
        return d
    d["ok"] = True
    rows = [r for r in rows if isinstance(r, dict)]
    d["rows_returned"] = len(rows)

    # 축 개수 oracle: 응답 C열 수
    c_cols = sorted({k for r in rows for k in r if _C_COL.match(k)}) if rows else []
    d["axis_cols"] = c_cols
    d["axis_count_meta"] = schema.axis_count
    d["axis_count_match"] = len(c_cols) == schema.axis_count

    # 코드 작동 + 라벨 정합
    row = find_cell_row(rows, period, match)
    d["cell_found"] = row is not None
    if row is not None:
        mism = []
        for col, nm in expect_nm.items():
            got = row.get(f"{col}_NM")
            if _norm(got) != _norm(nm):
                mism.append({"col": col, "meta": nm, "resp": got})
        d["label_mismatch"] = mism
        d["label_ok"] = not mism
    return d


def _verdict(parse: dict, data: dict, schema) -> tuple[str, list[str]]:
    notes: list[str] = []
    fail = False
    if not parse["ok"]:
        fail = True
        notes.append(f"파싱 불완전(흘린 행 {parse['dropped_rows']})")
    if data.get("skipped"):
        notes.append(f"교차검증 스킵: {data['skipped']}")
    elif data.get("error"):
        fail = True
        notes.append(f"데이터 호출 실패: {data['error']}")
    else:
        if not data.get("axis_count_match"):
            fail = True
            notes.append(
                f"축 수 불일치(메타 {data.get('axis_count_meta')} vs 응답 "
                f"{len(data.get('axis_cols', []))})"
            )
        if not data.get("cell_found"):
            notes.append("셀 0건(첫 값/최근시점 조합 데이터 없음)")
        elif not data.get("label_ok", True):
            notes.append(f"라벨 불일치: {data.get('label_mismatch')}")
    # 주기 플래그
    if not schema.periods:
        notes.append("주기 0개(PRD 실패 의심)")
    none_se = [p.se_label for p in schema.periods if p.se_code is None]
    if none_se:
        notes.append(f"se_code 매핑 누락: {none_se}")

    if fail:
        return "FAIL", notes
    return ("WARN", notes) if notes else ("PASS", notes)


async def _validate(org: str, tbl: str, name: str, key: str) -> dict:
    rec: dict = {"org_id": org, "tbl_id": tbl, "name": name}
    try:
        schema = await fetch_table_schema(org, tbl, key)
        raw_itm = await asyncio.to_thread(fetch_meta_item, org, tbl, "ITM", key)
    except Exception as exc:  # noqa: BLE001
        rec.update(verdict="FAIL", notes=[f"메타 조회 실패: {type(exc).__name__}: {exc}"])
        return rec
    parse = _check_parse(schema, raw_itm)
    data = await asyncio.to_thread(_check_data, schema, key)
    verdict, notes = _verdict(parse, data, schema)
    rec.update(
        verdict=verdict, notes=notes, parse=parse, data=data,
        item_count=len(schema.items), axis_count=schema.axis_count,
        period_count=len(schema.periods),
    )
    return rec


async def main() -> None:
    key = resolve_api_key()
    records = await asyncio.gather(
        *(_validate(o, t, n, key) for o, t, n in META_TEST_TABLES)
    )
    by = {"PASS": [], "WARN": [], "FAIL": []}
    for r in records:
        by[r["verdict"]].append(r)

    payload = {
        "summary": {
            "total": len(records),
            "PASS": len(by["PASS"]), "WARN": len(by["WARN"]), "FAIL": len(by["FAIL"]),
        },
        "results": records,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"총 {len(records)}표  PASS {len(by['PASS'])}  "
          f"WARN {len(by['WARN'])}  FAIL {len(by['FAIL'])}\n")
    icon = {"PASS": "✓", "WARN": "△", "FAIL": "✗"}
    for r in records:
        head = (f"{icon[r['verdict']]} {r['org_id']}/{r['tbl_id']}  "
                f"항목{r.get('item_count','?')}·축{r.get('axis_count','?')}·"
                f"주기{r.get('period_count','?')}  | {r['name']}")
        print(head)
        for n in r.get("notes", []):
            print(f"      - {n}")
    print(f"\n저장: {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
