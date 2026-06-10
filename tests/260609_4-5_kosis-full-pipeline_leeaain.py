"""KOSIS 전체 파이프라인 라이브 테스트 — claim → 검색 → 메타(ITM/PRD) → 최종 셀 조회.

claim 가정: 키워드="청년 실업률", 분류값(OBJ)="전국", 시점(PRD)="2023".

단계:
  1. search_tables(키워드)               → 통계표 후보 → org_id/tbl_id
  2. fetch_meta_item(.., "ITM"/"PRD")    → 항목·분류 메타 / 수록기간 메타
  3. ITM 의 OBJ_ID=="ITEM" 행            → ITM_ID = itmId
  4. ITM 의 OBJ_ID!="ITEM" & ITM_NM=="전국" 행 → ITM_ID = objL1
  5. PRD 메타에서 STRT_PRD_DE <= 2023 <= END_PRD_DE 검증, PRD_SE → prdSe
  6. statisticsParameterData.do 최종 요청 구성 + 조회 → DT 값

prdSe 는 예시 curl 의 'Y' 하드코딩 대신 PRD 메타의 PRD_SE 에서 가져온다.
(데이터 응답이 'A' 였던 A/Y 불확실성을 런타임에 해소한다.)

네트워크 + KOSIS_API_KEY(.env) 필요. 키 없으면 live skip. apiKey 는 출력 시 마스킹.

실행:
    uv run python tests/260609_4-5_kosis-full-pipeline_leeaain.py     # 단계별 상세 출력
    uv run pytest tests/260609_4-5_kosis-full-pipeline_leeaain.py -v

대상 모듈: src.kosis (search_tables / fetch_meta_item / build_params / call_kosis)
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-06-09
"""
from __future__ import annotations

import os
import re

import pytest
from dotenv import load_dotenv

from src.kosis import (
    KosisError,
    KosisQuery,
    build_params,
    call_kosis,
    fetch_meta_item,
    find_cell_row,
    search_tables,
    to_cell,
)
from src.kosis.client import DATA_URL

load_dotenv()

# ---- claim 가정 -------------------------------------------------------------
CLAIM_KEYWORD = "청년 실업률"   # 통계표 검색어 (항목 이름매칭에도 사용)
CLAIM_OBJ = "전국"             # 분류값 (행정구역별 등 분류축에서 찾을 값)
CLAIM_PRD = "2023"             # 수록 시점(연도)

# PRD 메타의 PRD_SE(한글 라벨) → 요청 prdSe 코드. 데이터 응답의 PRD_SE 는 또 다른
# 코드계('A'=년)라 셋이 서로 다름 — 메모리 kosis-prdse-three-representations.
# 라벨은 실측 확정(2026-06-09 샘플링): '년'→Y '분기'→Q '월'→M '반기'→H '일'→D,
# 'N년'(2년/3년…)→F. 'IR'(부정기)는 devGuide 문서값이나 샘플에서 미관측(라벨 추정).
_PRD_SE_CODE = {
    "년": "Y",      # STRT/END 표기 YYYY        (예: 2000)
    "분기": "Q",    #               YYYY n/4    (예: 1999 3/4)
    "월": "M",      #               YYYY.MM     (예: 1960.01)
    "반기": "H",    #               YYYY n/2    (예: 2022 1/2)
    "일": "D",      #               YYYYMMDD    (예: 19900302)
}


def _prd_se_code(label: str) -> str:
    """PRD 메타 라벨 → 요청 prdSe 코드. 'N년'(2·3·5년…)은 다년(F). 미지 라벨은 원본 반환."""
    label = (label or "").strip()
    if label in _PRD_SE_CODE:
        return _PRD_SE_CODE[label]
    if re.fullmatch(r"\d+년", label):    # '2년','3년','5년'… → 다년(F)
        return "F"
    return label                          # 미지 라벨: 그대로 보내 실패로 드러나게


# ---- 이름매칭 헬퍼 (resolve.py 규칙과 동일: 공백 제거 → 정확>부분) ----------

def _norm(s) -> str:
    """공백 제거 정규화. 이름 비교용."""
    return "".join(str(s or "").split())


def _match_id(rows, target):
    """rows 중 ITM_NM 이 target 과 일치(정확>부분)하는 행의 ITM_ID. 없으면 None."""
    t = _norm(target)
    if not t:
        return None
    for r in rows:                                   # 정확 일치 우선
        if _norm(r.get("ITM_NM")) == t:
            return r.get("ITM_ID")
    cands = [r for r in rows                          # 부분 일치(양방향)
             if t in _norm(r.get("ITM_NM")) or _norm(r.get("ITM_NM")) in t]
    cands.sort(key=lambda r: len(_norm(r.get("ITM_NM"))))  # 더 구체적(짧은) 우선
    return cands[0].get("ITM_ID") if cands else None


def _split_itm(itm_meta):
    """ITM 메타 → (items, axes_by_oid). items=OBJ_ID 'ITEM', 나머지는 분류축."""
    items: list[dict] = []
    axes: dict[str, list[dict]] = {}
    for r in itm_meta:
        if not isinstance(r, dict):
            continue
        oid = r.get("OBJ_ID")
        if oid == "ITEM":
            items.append(r)
        elif oid:
            axes.setdefault(oid, []).append(r)
    return items, axes


def _pick_prd_row(prd_meta, period):
    """PRD 메타에서 period 가 STRT_PRD_DE~END_PRD_DE 범위에 드는 행. 없으면 None.

    자릿수가 같은(주기 일치, 예: 연도 4자리) 행만 사전식 비교한다.
    다주기 표에서 월간(6자리) 행을 연도(4자리)와 헷갈리지 않으려는 것이다.
    """
    rows = prd_meta if isinstance(prd_meta, list) else [prd_meta]
    for r in rows:
        if not isinstance(r, dict):
            continue
        strt = str(r.get("STRT_PRD_DE", "")).strip()
        end = str(r.get("END_PRD_DE", "")).strip()
        if len(strt) == len(period) == len(end) and strt <= period <= end:
            return r
    return None


# ---- 단일 표 좌표 해소 → 최종 params ----------------------------------------

def _resolve_hit(hit, api_key):
    """단일 통계표(hit) → (params|None, info). info 는 단계별 결과(출력/디버깅용)."""
    info = {
        "tbl_id": hit.tbl_id, "org_id": hit.org_id, "tbl_nm": hit.tbl_nm,
        "itm_id": None, "obj_l1": None, "prd_se": None, "prd_range": None,
        "error": None,
    }
    try:
        itm_meta = fetch_meta_item(hit.org_id, hit.tbl_id, "ITM", api_key)
        prd_meta = fetch_meta_item(hit.org_id, hit.tbl_id, "PRD", api_key)
    except KosisError as exc:
        info["error"] = f"메타 조회 실패: {exc}"
        return None, info

    if not isinstance(itm_meta, list):
        info["error"] = f"ITM 메타 형식 비정상: {type(itm_meta).__name__}"
        return None, info

    items, axes = _split_itm(itm_meta)

    # [3] 항목 → itmId (1개면 그대로, 여러 개면 키워드로 이름매칭)
    info["itm_id"] = (items[0].get("ITM_ID") if len(items) == 1
                      else _match_id(items, CLAIM_KEYWORD))
    if info["itm_id"] is None:
        info["error"] = "항목(OBJ_ID=ITEM) 매칭 실패"
        return None, info

    # 이 테스트는 분류축 1개(예시 표 기준)만 지원 → objL1만 사용, objL2=""
    if len(axes) != 1:
        info["error"] = f"분류축 {len(axes)}개 — 단일 축만 지원: {sorted(axes)}"
        return None, info
    axis_rows = next(iter(axes.values()))

    # [4] 분류값 '전국' → objL1
    info["obj_l1"] = _match_id(axis_rows, CLAIM_OBJ)
    if info["obj_l1"] is None:
        info["error"] = f"분류값 매칭 실패: {CLAIM_OBJ!r}"
        return None, info

    # [5] PRD 범위 검증 + prdSe 결정(PRD 메타의 PRD_SE)
    prd_row = _pick_prd_row(prd_meta, CLAIM_PRD)
    if prd_row is None:
        info["error"] = f"수록기간 밖이거나 PRD 메타 없음: {CLAIM_PRD}"
        return None, info
    raw_se = str(prd_row.get("PRD_SE") or "").strip()   # 메타는 한글 라벨('년'…)
    info["prd_se_label"] = raw_se
    info["prd_se"] = _prd_se_code(raw_se)                # 요청 코드('Y'…)로 변환
    info["prd_range"] = (prd_row.get("STRT_PRD_DE"), prd_row.get("END_PRD_DE"))

    # [6] 최종 요청 params 구성 (objL2="" → 분류축 1개)
    query = KosisQuery(
        org_id=hit.org_id, tbl_id=hit.tbl_id, itm_id=info["itm_id"],
        period=CLAIM_PRD, period_se=info["prd_se"],
        obj_l1=info["obj_l1"], obj_l2="",
        match_filters={"C1": info["obj_l1"]},
    )
    return build_params(query, api_key), info


# ---- 파이프라인 (검색 → 후보 순회 → 첫 성공 표 조회) ------------------------

def run_pipeline(api_key, *, top_n=10, verbose=False):
    """검색 → 후보를 RANK 순으로 좌표 해소, 첫 성공 표에서 최종 조회.

    Returns dict: {hits, used, params, info, cell, attempts}.
    """
    hits = search_tables(CLAIM_KEYWORD, api_key, top_n=top_n)
    if verbose:
        print(f"[1] 검색 '{CLAIM_KEYWORD}': {len(hits)}건")
        for i, h in enumerate(hits, 1):
            print(f"    {i}. {h.org_id}/{h.tbl_id}  {h.tbl_nm}  ({h.prd_de})")
        print()

    attempts = []
    for hit in hits:
        params, info = _resolve_hit(hit, api_key)
        attempts.append(info)
        if verbose:
            _print_resolve(info)
        if params is None:
            continue
        rows = call_kosis(params)
        row = find_cell_row(rows, CLAIM_PRD, {"C1": info["obj_l1"]})
        try:
            cell = to_cell(row) if row else None
        except ValueError:
            cell = None                  # DT 가 숫자가 아닌 셀(-, ... 등)
        return {"hits": hits, "used": hit, "params": params,
                "info": info, "cell": cell, "attempts": attempts}
    return {"hits": hits, "used": None, "params": None,
            "info": None, "cell": None, "attempts": attempts}


# ---- 출력 헬퍼 (apiKey 절대 노출 금지) --------------------------------------

def _mask(params):
    return {k: ("[API_KEY_HIDDEN]" if k == "apiKey" else v)
            for k, v in params.items()}


def _to_curl(params):
    """최종 params → curl 문자열(apiKey 마스킹). 사람이 보고 확인용."""
    out = [f"curl -sG '{DATA_URL}' \\"]
    out += [f"  --data-urlencode '{k}={v}' \\" for k, v in _mask(params).items()]
    return "\n".join(out).rstrip(" \\")


def _print_resolve(info):
    tag = "✓" if info["error"] is None else "✗"
    print(f"[2-5] {tag} {info['org_id']}/{info['tbl_id']}  {info['tbl_nm']}")
    print(f"      itmId={info['itm_id']}  objL1={info['obj_l1']}  "
          f"prdSe={info['prd_se']!r}(라벨 {info.get('prd_se_label')!r})  "
          f"범위={info['prd_range']}")
    if info["error"]:
        print(f"      → skip: {info['error']}")


# ---- 라이브 pytest ----------------------------------------------------------

live = pytest.mark.skipif(
    not os.getenv("KOSIS_API_KEY"),
    reason="KOSIS_API_KEY 가 .env 에 없어 live 파이프라인 테스트를 건너뜀",
)


@live
def test_pipeline_reaches_dt_value():
    """claim(청년실업률·전국·2023) → 검색·메타·조회 끝에 DT 값(0~100%)에 도달."""
    result = run_pipeline(os.environ["KOSIS_API_KEY"])
    assert result["params"] is not None, (
        "좌표 해소 가능한 표를 못 찾음. 시도: "
        f"{[(a['tbl_id'], a['error']) for a in result['attempts']]}"
    )
    cell = result["cell"]
    assert cell is not None, "최종 셀 매칭 0건 (시점/분류 불일치)"
    assert isinstance(cell.value, float)
    assert cell.period == CLAIM_PRD
    assert 0.0 <= cell.value <= 100.0, f"실업률 % 범위를 벗어남: {cell.value}"


if __name__ == "__main__":
    if not os.getenv("KOSIS_API_KEY"):
        raise SystemExit("KOSIS_API_KEY 가 .env 에 없습니다.")
    key = os.environ["KOSIS_API_KEY"]
    print(f"claim 가정: 키워드={CLAIM_KEYWORD!r}  분류값={CLAIM_OBJ!r}  "
          f"시점={CLAIM_PRD!r}\n")

    result = run_pipeline(key, verbose=True)

    if result["params"] is None:
        print("\n[결과] 좌표 해소 가능한 표를 못 찾음.")
        raise SystemExit(1)

    print("\n[6] 최종 요청 (apiKey 마스킹):")
    print(_to_curl(result["params"]))

    cell, used, info = result["cell"], result["used"], result["info"]
    print("\n[7] 조회 결과:")
    if cell is None:
        print("    매칭 셀 없음 (None)")
    else:
        print(f"    표 {used.org_id}/{used.tbl_id}  ({used.tbl_nm})")
        print(f"    itmId={info['itm_id']}  objL1={info['obj_l1']}  {cell.period}")
        print(f"    → {cell.value} {cell.unit}  (원문 {cell.value_raw!r})")
