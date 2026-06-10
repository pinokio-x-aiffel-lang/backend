"""청년고용률 2024 도달 과정 추적: 표검색 → 메타조회 → 값조회 3단계.

KOSIS 파이프라인이 한 claim 을 한 셀 값(46.1%)으로 해소하는 과정을 추적한다.
KOSIS API 3번 호출의 요청·응답을 그대로 찍어 보여준다.
apiKey 는 절대 출력하지 않는다.

이 표(INH_1DA7015S)는 2축(시도별 + 연령계층별)이다.
population 을 연령밴드 "15 - 29세"로 주면, 시도축은 합계("계")로 폴백된다.
그리고 연령축이 15-29세 코드(75)로 매칭돼 좌표가 해소된다.
(population="전국" 처럼 시도값만 주면 연령축이 안 채워져 resolve 가 실패한다.)

각 단계 요청/응답 예시 (2024년 전국 청년고용률 = 46.1%):

  [1] 표검색  GET statisticsSearch.do
      요청 : searchNm=청년고용률, resultCount=10, sort=RANK
      응답 : [{ORG_ID:101, TBL_ID:INH_1DA7015S, TBL_NM:"청년고용률(시도)", ...}]  ← RANK 1위 선정

  [2] 메타조회  GET statisticsData.do  method=getMeta&type=ITM
      요청 : orgId=101, tblId=INH_1DA7015S
      응답 : [{OBJ_ID:"ITEM", ITM_ID:"T90", ITM_NM:"고용률"},
              {OBJ_ID:"A", OBJ_NM:"시도별",     ITM_ID:"00", ITM_NM:"계"}, ...,
              {OBJ_ID:"G", OBJ_NM:"연령계층별", ITM_ID:"75", ITM_NM:"15 - 29세"}]
      → 2축 구성(시도별 A + 연령계층별 G)을 이 메타 응답에서 그대로 알 수 있다.
      → 좌표해소: subject"청년고용률"→itmId=T90(부분일치 "고용률"),
                  population"15 - 29세"→ 시도축 objL1=00(계 폴백), 연령축 objL2=75

  [3] 값조회  GET Param/statisticsParameterData.do  method=getList
      요청 : itmId=T90, objL1=00, objL2=75, prdSe=Y, startPrdDe=endPrdDe=2024
      응답 : [{ITM_ID:T90, C1:"00",C1_NM:"계", C2:"75",C2_NM:"15 - 29세",
               PRD_DE:"2024", DT:"46.1", UNIT_NM:"%"}]
      → find_cell_row(PRD_DE=="2024" & C1=="00" & C2=="75") → to_cell → DT=46.1%

실행:  uv run x python tests/trace_youth_employment_2024.py

작성일: 2026-06-09
작성자: leeaain2027
"""
from __future__ import annotations

import json

from src.kosis.cell import build_params, find_cell_row, to_cell
from src.kosis.client import (
    DATA_URL,
    META_URL,
    SEARCH_URL,
    kosis_get,
    resolve_api_key,
)
from src.kosis.map_claim_to_cell import map_claim_to_cell_query_traced

KEY = resolve_api_key()
SUBJECT = "청년고용률"
POPULATION = "15 - 29세"   # 연령계층별 축 값(청년). 시도축은 합계("계")로 폴백.
PERIOD = "2024"
PERIOD_SE = "Y"


def _redact(params: dict) -> dict:
    return {k: ("***REDACTED***" if k == "apiKey" else v) for k, v in params.items()}


def _show(title: str, url: str, params: dict, resp) -> None:
    print(f"\n{'='*70}\n{title}\n{'='*70}")
    print(f"URL    : {url}")
    print(f"params : {json.dumps(_redact(params), ensure_ascii=False)}")
    print("응답   :")
    print(json.dumps(resp, ensure_ascii=False, indent=2)[:4000])


# ── 1단계: 표 검색 (statisticsSearch.do) ──────────────────────────────────────
search_params = {
    "method": "getList", "apiKey": KEY, "searchNm": SUBJECT,
    "startCount": "1", "resultCount": "10", "sort": "RANK",
}
hits = kosis_get(SEARCH_URL, search_params)
_show("[1] 표 검색  statisticsSearch.do", SEARCH_URL, search_params, hits[:1])
ORG_ID = str(hits[0]["ORG_ID"])
TBL_ID = str(hits[0]["TBL_ID"])
print(f"\n→ 선정 표: org={ORG_ID} tbl={TBL_ID}  {hits[0].get('TBL_NM')}")

# ── 2단계: 구조 메타 조회 (statisticsData.do?method=getMeta&type=ITM) ─────────
meta_params = {
    "method": "getMeta", "apiKey": KEY, "type": "ITM",
    "orgId": ORG_ID, "tblId": TBL_ID,
}
itm = kosis_get(META_URL, meta_params)
_show("[2] 메타 조회  statisticsData.do  getMeta type=ITM", META_URL, meta_params, itm)

# ── 좌표 해소: subject/population 이름매칭 → itmId/objL ────────────────────────
query, trace = map_claim_to_cell_query_traced(
    ORG_ID, TBL_ID, subject=SUBJECT, population=POPULATION,
    period=PERIOD, period_se=PERIOD_SE, api_key=KEY,
)
print(f"\n→ 좌표해소: itm_id={trace['itm_id']} obj_codes={trace['obj_codes']} "
      f"error={trace['error']}")
print(f"→ items={trace['items']}")
print(f"→ axes={ {k: len(v) for k, v in trace['axes'].items()} }  "
      f"(분류축 {len(trace['axes'])}개 — 메타로 2축 구조 확인됨)")
if query is None:
    raise SystemExit(f"좌표 해소 실패: {trace['error']}")
print(f"→ match_filters={query.match_filters}  objL1={query.obj_l1} objL2={query.obj_l2}")

# ── 3단계: 값 조회 (statisticsParameterData.do) — 단일 셀 ──────────────────────
data_params = build_params(query, KEY)
data_rows = kosis_get(DATA_URL, data_params, require_list=True)
_show("[3] 값 조회  statisticsParameterData.do  getList", DATA_URL, data_params, data_rows)

row = find_cell_row(data_rows, query.period, query.match_filters)
cell = to_cell(row) if row else None
print(f"\n{'='*70}\n최종 결과\n{'='*70}")
if cell:
    print(f"period={cell.period}  DT={cell.value}{cell.unit}  (raw={cell.value_raw!r})")
else:
    print("매칭 셀 없음")
