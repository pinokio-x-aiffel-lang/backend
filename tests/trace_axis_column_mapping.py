"""메타 축 순서(A,B,C…) ↔ 데이터 응답 컬럼(C1,C2,C3…) 대응이 표마다 성립하는지 검증.

resolve.py 가 match_filters 키를 f"C{i+1}" 로 합성하는데(메타 축 순서를 데이터 컬럼명에
대응), 이 가정이 표마다 성립하는지 확인하는 스크립트. 결론: 데이터 응답의 필드 키는
표 무관 C1/C2/… 고정(표마다 다른 건 표시명 C{k}_OBJ_NM 뿐)이라 합성이 안전.

여러 표에 대해:
  1) getMeta(ITM)에서 분류축(OBJ_ID != ITEM) 목록과 OBJ_NM/OBJ_ID_SN 확인
  2) 데이터 호출(objL 전부 ALL)에서 실제로 등장하는 C{k}_OBJ_NM 확인
  3) sorted(OBJ_ID) k번째 축의 OBJ_NM == 응답 C{k}_OBJ_NM 인지 비교

요청/응답 예시 (DT_1YL20531E, 1축):
  [메타] getMeta type=ITM → 분류축 A(OBJ_NM="행정구역별", OBJ_ID_SN=1)
  [값]   getList objL1=ALL → 응답 C-컬럼 {"C1": "행정구역별"}
  → 검증: 축1 A('행정구역별') ↔ C1('행정구역별')  ✅

실행:  uv run x python tests/trace_axis_column_mapping.py
주의:  TABLES 의 (prdSe, 시점)은 표마다 유효해야 함. 데이터 없으면(error 30)
       그 표는 컬럼 검증을 건너뜀(매핑 로직 문제가 아니라 시점 불일치).

작성일: 2026-06-09
작성자: leeaain2027
"""
from __future__ import annotations

from src.kosis.client import DATA_URL, kosis_get, resolve_api_key

KEY = resolve_api_key()

# (orgId, tblId, prdSe, 한 시점) — 축 개수가 다양한 표들
TABLES = [
    ("101", "DT_1YL20531E", "Y", "2023"),   # 1축: 행정구역별
    ("101", "DT_1DE9046S", "Y", "2023"),     # 다축 후보: 연령별 경제활동상태
    ("101", "DT_1DA7004S", "M", "202401"),   # 성별/연령별 실업률(있으면 다축)
]


def axes_from_meta(org, tbl):
    itm = kosis_get(
        "https://kosis.kr/openapi/statisticsData.do",
        {"method": "getMeta", "apiKey": KEY, "type": "ITM",
         "orgId": org, "tblId": tbl},
    )
    axes = {}
    for r in itm:
        oid = r.get("OBJ_ID")
        if oid and oid != "ITEM":
            axes.setdefault(oid, []).append(r)
    # OBJ_ID -> (OBJ_NM, OBJ_ID_SN, n_values, sample first code)
    return {
        oid: (
            rows[0].get("OBJ_NM"),
            rows[0].get("OBJ_ID_SN"),
            len(rows),
            rows[0].get("ITM_ID"),
        )
        for oid, rows in axes.items()
    }


def data_columns(org, tbl, prd_se, prd, n_axes):
    params = {
        "method": "getList", "apiKey": KEY, "orgId": org, "tblId": tbl,
        "prdSe": prd_se, "startPrdDe": prd, "endPrdDe": prd,
        "itmId": "ALL",
    }
    for k in range(1, n_axes + 1):
        params[f"objL{k}"] = "ALL"
    params["objL"] = "ALL"
    try:
        rows = kosis_get(DATA_URL, params, require_list=True)
    except Exception as e:  # noqa: BLE001
        return None, f"data 호출 실패: {e}"
    if not rows:
        return None, "응답 0행"
    r0 = rows[0]
    cols = {}
    for k in range(1, 8):
        nm = r0.get(f"C{k}_OBJ_NM")
        if nm is not None or f"C{k}" in r0:
            cols[f"C{k}"] = nm
    return cols, None


for org, tbl, prd_se, prd in TABLES:
    print(f"\n{'='*70}\n{tbl}\n{'='*70}")
    try:
        axes = axes_from_meta(org, tbl)
    except Exception as e:  # noqa: BLE001
        print(f"  meta 실패: {e}")
        continue
    sorted_ids = sorted(axes)
    print(f"  메타 분류축 (sorted OBJ_ID): {sorted_ids}")
    for i, oid in enumerate(sorted_ids):
        nm, sn, n, first = axes[oid]
        print(f"    [{i+1}] OBJ_ID={oid}  OBJ_NM={nm!r}  OBJ_ID_SN={sn}  "
              f"값수={n}  첫코드={first!r}")

    cols, err = data_columns(org, tbl, prd_se, prd, len(sorted_ids))
    if err:
        print(f"  데이터 컬럼: {err}")
        continue
    print(f"  데이터 응답 C-컬럼: {cols}")
    # 대응 검증: sorted 축 k번째 OBJ_NM == 응답 C{k}_OBJ_NM ?
    print("  대응 검증:")
    for i, oid in enumerate(sorted_ids):
        meta_nm = axes[oid][0]
        data_nm = cols.get(f"C{i+1}")
        ok = "✅" if meta_nm == data_nm else "❌"
        print(f"    축{i+1} {oid}({meta_nm!r})  ↔  C{i+1}({data_nm!r})  {ok}")
