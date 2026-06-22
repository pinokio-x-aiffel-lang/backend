from __future__ import annotations

import asyncio
import json
import logging
import time

from src.kosis.client import KosisError, kosis_get, resolve_api_key
from src.kosis.search import SearchHit, search_tables
from src.llm.client import LlmError
from src.llm.model_presets import NAVIGATE_TREE
from src.observability.tracing import traced_chat
from src.prompts.prompts import NAVIGATE_TREE_SYSTEM, NAVIGATE_TREE_USER
from src.schemas.runtime import (
    Claim,
    ClaimAnalysis,
    KosisCandidate,
    KosisQuery,
    KosisSearch,
    MasterSchema,
)

logger = logging.getLogger("kosis")

"""
후보 표 찾기 — 하이브리드:
  (1) 분류 트리(statisticsList.do)를 LLM 으로 '통계조사'까지 드릴다운해 스코프를 정하고,
  (2) 그 조사 스코프 안에서 키워드 검색(statisticsSearch.do)으로 항목 인식 후보를 모은다.

트리만으론 '고용률·실업률' 같은 파생지표가 '총괄' 표의 항목(컬럼)으로 숨어 폴더명에
안 드러나 못 잡는다(recall 한계). 키워드 검색은 CONTENTS(항목명 포함)를 매칭해 이를
잡지만 도메인이 섞인다 — 트리로 조사를 좁혀 그 약점을 보완한다.
"""

_LIST_API = "statisticsList.do"
_LIST_URL = "https://kosis.kr/openapi/statisticsList.do"
_SEARCH_API = "statisticsSearch.do"
_DATA_API = "statisticsData.do"  # [5] placeholder query 표시용(값은 [5]가 덮어씀)

# 트리/검색 정합: 키워드 검색 hit 의 FULL_PATH_ID 가 '주제별(MT_ZTITLE)' 분류 경로라,
# 스코핑하려면 트리도 주제별로 고정해야 한다(기관별 등은 경로 체계가 달라 매칭 불가).
_VW_CD = "MT_ZTITLE"

TOP_N = 10          # [5]로 넘길 최종 후보 상한
BEAM_WIDTH = 3      # 각 트리 level 에서 LLM 이 고르는 분류 수(빔 폭)
KEYWORD_TOP_N = 100  # 키워드 검색 후보 풀(스코핑 전). 넉넉히 받아 조사 스코프로 거른다.

# subject 앞 국가 한정어는 KOSIS 키워드 오염 원인 → 제거(공백은 보존해 토크나이즈 유지).
_SUBJECT_DROP_PREFIXES = ("한국 ", "한국의 ", "우리나라 ", "우리나라의 ")

# LLM 응답 구조(structured outputs): 고른 분류 index 배열(최대 BEAM_WIDTH개, 빈 배열 허용).
_PICK_SCHEMA = {
    "type": "object",
    "properties": {
        "chosen_indices": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["chosen_indices"],
}


class RetrieveKosisCandidatesError(Exception):
    """KOSIS 후보 통계표 검색 실패."""


async def retrieve_kosis_candidates(master_schema: MasterSchema) -> None:
    """
    [4] Retrieve KOSIS Candidates — 트리 스코핑 + 키워드 검색 하이브리드.

    Input:
        master_schema.claims         # subject / population / period 등

    Output:
        master_schema.analysis       # claim별 ClaimAnalysis 초기화
                                      #   - kosis_search : 탐색/검색 로그
                                      #   - candidates   : 조사 스코프 내 후보 표(≤TOP_N)
                                      #   - kosis_query  : placeholder ([5]에서 채움)

    Responsibility:
        claim별로 (1) 분류 트리를 LLM 으로 '통계조사' 노드까지 좁히고, (2) 그 조사
        스코프(FULL_PATH_ID) 안에서 subject 키워드 검색 결과만 후보로 남긴다.
        '가장 적합한 1개' 선정은 [5] itmId 매칭·[6] rank_evidence 의 몫.

        한 claim 의 실패(KosisError/ValueError)는 success=0 + error_msg 로 기록하고
        계속 진행한다(한 건이 전체 파이프라인을 막지 않게). 그 외 예외만 raise.
    """
    api_key = resolve_api_key()  # 키 1회 확보(없으면 ValueError → runner 가 처리)
    master_schema.analysis = list(
        await asyncio.gather(
            *(_search_one_claim(claim, api_key) for claim in master_schema.claims)
        )
    )


async def _search_one_claim(claim: Claim, api_key: str) -> ClaimAnalysis:
    """claim 1건 → 조사 스코핑 + 키워드 검색 → ClaimAnalysis (후보 풀 포함)."""
    keyword = _preprocess_subject(claim.subject or "")
    period = f"{claim.period_type}:{claim.period_value.llm_value}"
    t0 = time.perf_counter()
    try:
        # 트리 스코핑과 키워드 검색은 독립이라 동시에.
        survey_ids, major_ids = await _navigate_to_surveys(
            claim, keyword, period, api_key
        )
        hits = await asyncio.to_thread(search_tables, keyword, top_n=KEYWORD_TOP_N)
    except (KosisError, ValueError) as exc:
        return _analysis(
            claim.claim_id, keyword, candidates=[],
            success=0, error_msg=str(exc), duration_ms=_ms_since(t0),
        )

    # 조사 스코프로 거른다. 비면 대분류로 완화, 그래도 비면 무스코프(최후 — [6]이 재정렬).
    scoped = _scope_hits(hits, survey_ids)
    scope = "survey"
    if not scoped and major_ids:
        scoped, scope = _scope_hits(hits, major_ids), "major"
    if not scoped:
        scoped, scope = hits, "unscoped"
    candidates = scoped[:TOP_N]

    logger.info(
        "KOSIS 후보 '%s': 검색 %d건 → %s 스코프 %d건 (조사=%s)",
        keyword, len(hits), scope, len(candidates), sorted(survey_ids) or "(없음)",
    )
    err = None if candidates else "스코프 내 후보 0건"
    return _analysis(
        claim.claim_id, keyword, candidates=candidates,
        success=1 if candidates else 0, error_msg=err, duration_ms=_ms_since(t0),
    )


async def _navigate_to_surveys(
    claim: Claim, keyword: str, period: str, api_key: str
) -> tuple[set[str], set[str]]:
    """주제별 트리를 2단계(대분류 → 통계조사) 내려가 스코프 LIST_ID 집합을 정한다.

    Returns:
        (survey_ids, major_ids) — 통계조사 LIST_ID 들과 대분류 LIST_ID 들.
        키워드 검색 hit 의 FULL_PATH_ID 경로 세그먼트와 교집합으로 스코핑한다.
        LLM 이 한 단계도 못 고르면 빈 집합(→ 호출부가 무스코프로 폴백).
    """
    # [대분류] MT_ZTITLE 최상위 30개 중 subject 관련 top-3.
    majors = _folders(await asyncio.to_thread(_list_children, _VW_CD, None, api_key))
    major_picks = await _llm_pick(
        claim, keyword, period, "(최상위 — 통계 대분류)",
        [_node_label(r) for r in majors],
    )
    chosen_majors = [majors[i] for i in major_picks]
    logger.info(
        "KOSIS 스코프 '%s' 대분류: %s", keyword,
        [_node_label(r) for r in chosen_majors] or "(기권)",
    )
    if not chosen_majors:
        return set(), set()
    major_ids = {str(r.get("LIST_ID", "")) for r in chosen_majors}

    # [통계조사] 고른 대분류들의 자식(조사) 풀에서 subject 관련 top-3.
    child_lists = await asyncio.gather(
        *(asyncio.to_thread(_list_children, _VW_CD, str(r.get("LIST_ID", "")), api_key)
          for r in chosen_majors)
    )
    surveys = [r for rows in child_lists for r in _folders(rows)]
    survey_picks = await _llm_pick(
        claim, keyword, period,
        "상위: " + ", ".join(_node_label(r) for r in chosen_majors),
        [_node_label(r) for r in surveys],
    )
    chosen_surveys = [surveys[i] for i in survey_picks]
    logger.info(
        "KOSIS 스코프 '%s' 통계조사: %s", keyword,
        [_node_label(r) for r in chosen_surveys] or "(기권)",
    )
    survey_ids = {str(r.get("LIST_ID", "")) for r in chosen_surveys}
    return survey_ids, major_ids


def _scope_hits(hits: list[SearchHit], ids: set[str]) -> list[SearchHit]:
    """FULL_PATH_ID 경로에 스코프 LIST_ID 가 포함된 hit 만 남긴다(RANK 순 보존)."""
    if not ids:
        return []
    return [h for h in hits if _path_ids(h) & ids]


def _path_ids(hit: SearchHit) -> set[str]:
    """검색 hit 의 FULL_PATH_ID('D > D_2 > B17') → 경로 세그먼트 집합."""
    path = str((hit.raw or {}).get("FULL_PATH_ID", ""))
    return {seg.strip() for seg in path.split(">") if seg.strip()}


def _list_children(vw_cd: str, parent_list_id: str | None, api_key: str) -> list[dict]:
    """분류 트리 한 노드의 자식 목록 조회(statisticsList.do).

    parent_list_id 가 None 이면 vwCd 의 최상위 분류. 폴더는 LIST_ID/LIST_NM,
    표(leaf)는 TBL_ID/ORG_ID/TBL_NM 을 가진다(한 응답에 섞여 올 수 있음).
    """
    params = {"method": "getList", "apiKey": api_key, "vwCd": vw_cd}
    if parent_list_id:
        params["parentListId"] = parent_list_id
    try:
        return kosis_get(_LIST_URL, params)
    except KosisError as exc:
        # 자식 없는 노드엔 KOSIS 가 err 30("데이터가 존재하지 않습니다")으로 응답한다.
        # 빈 분기로 취급(그 외 오류 — 인증 등 — 는 전파).
        if str(exc).startswith("30:") or "데이터가 존재하지 않" in str(exc):
            return []
        raise


def _folders(rows: list[dict]) -> list[dict]:
    """자식 목록에서 하위 분류(폴더)만. 표(leaf)는 스코핑엔 쓰지 않는다."""
    return [r for r in rows if not _is_table(r)]


def _is_table(row: dict) -> bool:
    """leaf(통계표) 판별 — TBL_ID 가 있으면 표, 없으면 하위 분류(폴더)."""
    return bool(str(row.get("TBL_ID", "")).strip())


def _node_label(row: dict) -> str:
    """LLM 보기에 쓸 노드 이름(표=TBL_NM, 폴더=LIST_NM)."""
    return str(row.get("TBL_NM") or row.get("LIST_NM") or "").strip()


def _preprocess_subject(subject: str) -> str:
    """키워드 전처리: 국가 한정 접두어 제거(공백은 보존 — 검색 토크나이즈 유지)."""
    s = subject.strip()
    for prefix in _SUBJECT_DROP_PREFIXES:
        if s.startswith(prefix):
            return s[len(prefix):].strip()
    return s


async def _llm_pick(
    claim: Claim, keyword: str, period: str, breadcrumb: str, options: list[str]
) -> list[int]:
    """분류 목록 중 subject 에 맞는 top-3 index 를 LLM 으로 고른다(to_thread)."""
    if not options:
        return []
    return await asyncio.to_thread(
        _llm_pick_sync, claim, keyword, period, breadcrumb, options
    )


def _llm_pick_sync(
    claim: Claim, keyword: str, period: str, breadcrumb: str, options: list[str]
) -> list[int]:
    """닫힌 보기(분류 index) 중 top-3 선택. 실패/기권/범위초과는 걸러내고 빈 배열."""
    opt_text = "\n".join(f"  [{i}] {name}" for i, name in enumerate(options))
    messages = [
        {"role": "system", "content": NAVIGATE_TREE_SYSTEM},
        {"role": "user", "content": NAVIGATE_TREE_USER.format(
            subject=keyword or claim.subject,
            population=claim.population, unit=claim.unit, period=period,
            breadcrumb=breadcrumb, options=opt_text,
        )},
    ]
    try:
        resp = traced_chat(
            model_alias=NAVIGATE_TREE.model_alias,
            model_name=NAVIGATE_TREE.model_name,
            messages=messages,
            max_tokens=NAVIGATE_TREE.max_tokens,
            temperature=NAVIGATE_TREE.temperature,
            json_structure=_PICK_SCHEMA,
            trace_name="retrieve_kosis_candidates:navigate",
        )
        data = json.loads(resp.text.strip())
    except (LlmError, AttributeError, json.JSONDecodeError):
        return []
    idxs = data.get("chosen_indices")
    if not isinstance(idxs, list):
        return []
    out: list[int] = []
    for x in idxs:  # 범위 밖·중복·과잉(>BEAM_WIDTH) 방어
        if isinstance(x, int) and 0 <= x < len(options) and x not in out:
            out.append(x)
        if len(out) >= BEAM_WIDTH:
            break
    return out


def _analysis(
    claim_id: str,
    keyword: str,
    *,
    candidates: list[SearchHit],
    success: int,
    error_msg: str | None,
    duration_ms: int,
) -> ClaimAnalysis:
    # 선정은 [5]/[6]의 몫. RANK 1위를 임시 선정값으로 둬 [5]가 동작하게 한다.
    top = candidates[0] if candidates else None
    return ClaimAnalysis(
        claim_id=claim_id,
        kosis_search=KosisSearch(
            api=_SEARCH_API,
            query=keyword,
            params=_params_log(keyword),
            hits=len(candidates),
            selected_tbl_id=top.tbl_id if top else None,
            selected_tbl_name=top.tbl_nm if top else None,
            success=success,
            error_msg=error_msg,
            duration_ms=duration_ms,
        ),
        candidates=[_candidate(h) for h in candidates],
        kosis_query=_placeholder_query(),
    )


def _candidate(hit: SearchHit) -> KosisCandidate:
    return KosisCandidate(
        org_id=hit.org_id,
        tbl_id=hit.tbl_id,
        tbl_nm=hit.tbl_nm,
        org_nm=hit.org_nm,
        stat_nm=hit.stat_nm,
        prd_de=hit.prd_de,
    )


def _placeholder_query() -> KosisQuery:
    """[5] fetch_kosis_data 가 채울 자리. 미조회 상태(success=0)."""
    return KosisQuery(
        api=_DATA_API,
        tbl_id="",
        params="",
        rows_returned=0,
        success=0,
        duration_ms=0,
    )


def _params_log(keyword: str) -> str:
    """탐색/검색 설정을 로그용 JSON 으로. apiKey 는 절대 포함하지 않는다."""
    return json.dumps(
        {
            "strategy": "tree-scoped-search",
            "list_api": _LIST_API,
            "search_api": _SEARCH_API,
            "vw_cd": _VW_CD,
            "subject": keyword,
            "beam_width": BEAM_WIDTH,
            "keyword_top_n": KEYWORD_TOP_N,
        },
        ensure_ascii=False,
    )


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
