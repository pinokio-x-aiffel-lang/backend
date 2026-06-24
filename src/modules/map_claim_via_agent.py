"""[4+5 대안 경로 v2] SKILL.md 기반 agent — 추론+툴콜링 단일 호출 또는 Think→Act 분리.

GPT 계열: think_preset 단일 호출(추론+툴콜 동시).
HCX-007 : act_preset 지정 시 Think(추론, thinking_effort) → Act(function_calling) 분리.

Python 모듈 역할:
  - SKILL.md 시스템 프롬프트 제공
  - 툴 정의 + 실행 (search / meta / cell / report_result / report_not_found)
  - 에이전트 루프 (LLM 호출 → 툴 실행 → 반복, 최대 _MAX_TURNS)
  - report_result 호출 시 Evidence 생성

기존 Pipeline.run() 및 map_claim_via_meta 불변.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from pathlib import Path
from typing import Any

from src.embedding.clova_client import ClovaEmbeddingClient, EmbeddingError
from src.kosis import (
    KosisError,
    call_kosis,
    fetch_table_metadata,
    resolve_api_key,
    search_tables,
)
from src.kosis.search import SearchHit
from src.llm.model_presets import MAP_CLAIM_AGENT, MAP_CLAIM_ACT, MAP_CLAIM_THINK, ModelPreset
from src.observability.tracing import traced_chat
from src.schemas.runtime import (
    Claim,
    ClaimAnalysis,
    Evidence,
    KosisQuery,
    KosisSearch,
    MasterSchema,
)

logger = logging.getLogger("kosis.agent")

# ReAct 에이전트 전용 버전 (tool calling 구조에 맞춰 수정).
# 원본 SKILL.md는 map_claim_via_meta.py(structured output 단일 선택) 경로용.
_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / ".claude" / "skills" / "kosis-lookup" / "SKILL.agent.md"
)
# Think 전용 프롬프트 — 자연어 분석만, JSON/도구호출 금지.
# Act는 기존 SKILL.MD 기반, Think는 이 파일 기반으로 분리.
_THINK_MD = (
    Path(__file__).resolve().parents[2]
    / ".claude" / "skills" / "kosis-lookup" / "THINK.md"
)
_MAX_TURNS = 10
_SEARCH_TOP_N = 30
_META_TOP_K = 15

_SEARCH_API = "kosis/statisticsSearch.do"
_DATA_API = "kosis/statisticsParameterData.do"

_ACT_TRIGGER = "위 분석을 바탕으로 적절한 도구를 호출하라."


def _empty_search() -> KosisSearch:
    return KosisSearch(
        api=_SEARCH_API, query="", params="agent",
        hits=0, success=0, duration_ms=0,
    )


def _empty_query(tbl_id: str = "") -> KosisQuery:
    return KosisQuery(
        api=_DATA_API, tbl_id=tbl_id, params="",
        rows_returned=0, success=0, duration_ms=0,
    )


# ── 툴 스키마 ─────────────────────────────────────────────────────────────────
_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_kosis_tables",
            "description": "키워드로 KOSIS 통계표를 검색한다. 국내 전국조사 우선 정렬.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "keyword": {"type": "string", "description": "검색 키워드 (예: '산업별 취업자')"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_metadata",
            "description": "통계표의 항목(itmId)과 분류축(objL) 코드 목록을 조회한다.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "org_id": {"type": "string", "description": "기관 코드 (예: '101')"},
                    "tbl_id": {"type": "string", "description": "통계표 ID (예: 'DT_1DA7001S')"},
                },
                "required": ["org_id", "tbl_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_kosis_cell",
            "description": (
                "KOSIS 통계표에서 특정 항목·기간의 셀 값을 조회한다. "
                "objL 레벨 불일치는 자동 재시도한다. "
                "org_id는 검색 결과의 org= 값 그대로 사용(통계청=101). "
                "axis_codes를 모르면 빈 배열([])로 두면 자동 처리."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "org_id": {"type": "string", "description": "기관 코드 (예: '101')"},
                    "tbl_id": {"type": "string"},
                    "itm_id": {"type": "string", "description": "항목 코드 (예: 'T30')"},
                    "period": {"type": "string", "description": "기간 (예: '2025-03'=월간, '2025'=연간)"},
                    "period_type": {"type": "string", "description": "월간=M, 연간=Y, 분기=Q"},
                    "axis_codes": {
                        "type": "array",
                        "description": "분류축 코드 목록. 모르면 빈 배열 []",
                        "items": {
                            "type": "object",
                            "properties": {
                                "obj_id": {"type": "string"},
                                "code": {"type": "string"},
                            },
                            "required": ["obj_id", "code"],
                        },
                    },
                },
                "required": ["org_id", "tbl_id", "itm_id", "period", "period_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_result",
            "description": "KOSIS 셀 값을 확인했을 때 최종 결과를 보고한다.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "value": {"type": "number"},
                    "tbl_id": {"type": "string"},
                    "org_id": {"type": "string"},
                    "itm_id": {"type": "string"},
                    "unit": {"type": "string"},
                    "period": {"type": "string"},
                },
                "required": ["value", "tbl_id", "org_id", "itm_id", "unit", "period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_not_found",
            "description": "적합한 KOSIS 셀을 찾지 못했을 때 호출한다.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
]


# ── 툴 실행 ───────────────────────────────────────────────────────────────────
def _survey_tier(hit: SearchHit) -> int:
    nm = (hit.stat_nm or hit.tbl_nm or "").lower()
    tid = (hit.tbl_id or "").upper()
    if any(k in nm for k in ("지역별고용", "시도", "시군구", "지방지표", "지역고용")):
        return 1
    if any(k in nm for k in ("oecd", "imf", "un ", "world bank", "국제통계")) or tid.startswith("DT_2"):
        return 2
    return 0


# ── 검색 결과 임베딩 재랭킹 (B 전용) ──────────────────────────────────────────
# search_tables 가 준 후보(_SEARCH_TOP_N)를 keyword↔표명 의미유사도로 재정렬해
# 상위 _META_TOP_K 만 LLM 에 보여준다. survey_tier 단독 정렬은 정답 표가 15위 밖이면
# LLM 시야에서 잘려 못 고르던 누수를 풀기 위함. 임베딩은 LLM(생성) 호출이 아니라
# 벡터 서비스 — src/embedding 전용 클라이언트 사용. 키 없음·호출 실패 시 None 을 돌려
# _exec_search 가 기존 survey_tier 폴백으로 복귀한다(회귀 안전).
_EMB_RERANK = os.environ.get("KOSIS_AGENT_EMB_RERANK", "1") != "0"
_EMB_CLIENT: ClovaEmbeddingClient | None = None
_EMB_CACHE: dict[str, list[float]] = {}   # tbl_id → 표명 임베딩(세션 캐시)
_EMB_DISABLED = False                      # 키 없음/반복 실패 시 세션 내 재시도 중단


def _embed_client() -> ClovaEmbeddingClient | None:
    global _EMB_CLIENT, _EMB_DISABLED
    if _EMB_DISABLED or not _EMB_RERANK:
        return None
    if _EMB_CLIENT is None:
        key = os.environ.get("CLOVASTUDIO_API_KEY", "")
        if not key:
            logger.warning("임베딩 재랭킹 비활성: CLOVASTUDIO_API_KEY 없음 → survey_tier 폴백")
            _EMB_DISABLED = True
            return None
        _EMB_CLIENT = ClovaEmbeddingClient(api_key=key)
    return _EMB_CLIENT


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _rerank_by_embedding(keyword: str, hits: list[SearchHit]) -> list[SearchHit] | None:
    """keyword↔(표명+조사명) 코사인으로 hits 재정렬(동점=survey_tier). 불가 시 None(폴백)."""
    global _EMB_DISABLED
    client = _embed_client()
    if client is None or not hits or not keyword.strip():
        return None
    try:
        q = client.embed(keyword).vector
        scored: list[tuple[float, SearchHit]] = []
        for h in hits:
            vec = _EMB_CACHE.get(h.tbl_id)
            if vec is None:
                text = f"{h.tbl_nm} {h.stat_nm or ''}".strip()
                vec = client.embed(text).vector
                _EMB_CACHE[h.tbl_id] = vec
            scored.append((_cosine(q, vec), h))
    except EmbeddingError as e:
        logger.warning("임베딩 재랭킹 실패(survey_tier 폴백): %s", e)
        _EMB_DISABLED = True   # 반복 실패 방지 — 세션 내 폴백 고정
        return None
    scored.sort(key=lambda sh: (-sh[0], _survey_tier(sh[1])))
    return [h for _, h in scored]


def _exec_search(keyword: str) -> str:
    try:
        hits = search_tables(keyword, top_n=_SEARCH_TOP_N)
    except Exception as e:
        return f"검색 오류: {e}"
    reranked = _rerank_by_embedding(keyword, hits)
    hits = reranked if reranked is not None else sorted(hits, key=_survey_tier)
    lines = [
        f"org={h.org_id} tbl={h.tbl_id} | {h.tbl_nm} ({h.stat_nm or ''})"
        for h in hits[:_META_TOP_K]
    ]
    return "\n".join(lines) if lines else "검색 결과 없음"


def _exec_meta(org_id: str, tbl_id: str) -> str:
    try:
        meta = fetch_table_metadata(org_id, tbl_id)
    except Exception as e:
        return f"메타 조회 실패: {e}"
    items_str = "; ".join(
        f"{it.itm_id}={it.itm_nm}" + (f"({it.unit})" if it.unit else "")
        for it in meta.items[:25]
    )
    axes = []
    for ax in meta.axes:
        vals = "; ".join(f"{c}={n}" for c, n in ax.values[:30])
        axes.append(f"축[{ax.name}/{ax.obj_id}]: {vals}")
    prd = ", ".join(p.se_code or p.se_label for p in meta.periods) or "?"
    return f"주기: {prd}\n항목: {items_str}\n" + "\n".join(axes)


def _exec_cell(
    org_id: str, tbl_id: str, itm_id: str,
    period: str, period_type: str,
    axis_codes: list[dict],
) -> str:
    # HCX-005가 인자를 int로 넘기는 경우 방어
    org_id = str(org_id) if org_id is not None else ""
    tbl_id = str(tbl_id) if tbl_id is not None else ""
    itm_id = str(itm_id) if itm_id is not None else ""
    if org_id in ("001", "", None, "None"):
        org_id = "101"
    prd = str(period).replace("-", "")
    if period_type == "Y":
        prd = prd[:4]
    # axis_codes 항목이 dict가 아닌 경우(str/int) 방어
    axis_codes = [ac for ac in (axis_codes or []) if isinstance(ac, dict)]
    n = len(axis_codes)
    chosen = {ac.get("code", "") for ac in axis_codes}
    api_key = resolve_api_key()

    for n_try in [n, n + 1, n + 2, n - 1]:
        if n_try < 0:
            continue
        params: dict[str, Any] = {
            "method": "getList",
            "apiKey": api_key,
            "orgId": org_id, "tblId": tbl_id, "itmId": itm_id,
            "prdSe": period_type, "startPrdDe": prd, "endPrdDe": prd,
        }
        for i in range(1, n_try + 1):
            params[f"objL{i}"] = "ALL"
        try:
            rows = call_kosis(params)
        except KosisError as e:
            if any(c in str(e) for c in ("20:", "21:", "30:")):
                continue
            return f"KOSIS 오류: {e}"
        except Exception as e:
            return f"조회 오류: {e}"
        if not rows:
            continue
        best: dict | None = None
        best_score = -1
        for row in rows:
            if row.get("ITM_ID") != itm_id:
                continue
            ck_nms = {row.get(f"C{i}_NM", "") for i in range(1, 6)}
            ck_codes = {row.get(f"C{i}", "") for i in range(1, 6)}
            matched = sum(1 for c in chosen if c in ck_nms or c in ck_codes)
            kye = sum(1 for nm in ck_nms if nm in ("계", "합계", "전체", "전국", ""))
            score = matched * 100 + kye
            if score > best_score:
                best, best_score = row, score
        if best:
            val = best.get("DT")
            unit = best.get("UNIT") or ""
            unit_str = f" (단위: {unit})" if unit else ""
            try:
                return f"값: {float(val)}{unit_str}"
            except (TypeError, ValueError):
                return f"값: {val}{unit_str}"
        # itm_id가 있는 행이 없음 → 가용 itm_id 목록 반환해 Think가 재시도할 수 있게
        if rows:
            available = sorted({r.get("ITM_ID", "") for r in rows if r.get("ITM_ID")})
            return f"셀 조회 실패: itm_id={itm_id!r} 없음. 가용 항목: {available[:10]}"
    return "셀 조회 실패: 데이터 없음 (period/tbl_id 확인 필요)"


def _exec_tool(fn: str, args: dict, cell_history: list[tuple[str, str, str]]) -> str:
    """툴 이름·인자 → 실행 결과 문자열. cell_history는 fetch_kosis_cell 결과 추적용."""
    if fn == "search_kosis_tables":
        return _exec_search(args.get("keyword", ""))
    if fn == "get_table_metadata":
        return _exec_meta(args.get("org_id", "101"), args.get("tbl_id", ""))
    if fn == "fetch_kosis_cell":
        result = _exec_cell(
            args.get("org_id", "101"), args.get("tbl_id", ""),
            args.get("itm_id", ""), args.get("period", ""),
            args.get("period_type", "M"), args.get("axis_codes") or [],
        )
        cell_history.append((fn, json.dumps(args, ensure_ascii=False)[:80], result))
        return result
    return f"알 수 없는 툴: {fn}"


def _parse_args(raw) -> dict:
    result = json.loads(raw) if isinstance(raw, str) else (raw or {})
    # json.loads가 dict 아닌 값(str/int/list) 반환 시 안전하게 {} 반환
    return result if isinstance(result, dict) else {}


# ── 메시지 빌더 ───────────────────────────────────────────────────────────────
def _claim_user_msg(claim: Claim) -> str:
    """claim 정보 user 메시지 (Think/Act 공용)."""
    cmp = ""
    if claim.compare_period_value and claim.compare_period_value.llm_value:
        cmp = f"\n비교기준기간(compare_period): {claim.compare_period_value.llm_value}"
    return (
        f"주제: {claim.subject}\n모집단: {claim.population}\n"
        f"단위: {claim.unit}\n"
        f"기간(period): {claim.period_value.llm_value}\n"
        f"기간유형(period_type): {claim.period_type}{cmp}\n"
        f"주장수치: {claim.value.llm_value}\n주장유형: {claim.claim_type.value}"
    )


def _build_think_messages(claim: Claim) -> tuple[dict, dict]:
    """Think 전용 메시지 — THINK.md 기반 자연어 분석 전용."""
    think_md = _THINK_MD.read_text(encoding="utf-8")
    system = {"role": "system", "content": think_md}
    user = {"role": "user", "content": _claim_user_msg(claim)}
    return system, user


def _build_messages(claim: Claim) -> tuple[dict, dict]:
    """Act 전용 메시지 — SKILL.md 기반 도구 호출."""
    skill_md = _SKILL_MD.read_text(encoding="utf-8")
    system = (
        skill_md + "\n\n---\n"
        "위 SKILL.md 절차에 따라 claim의 KOSIS 공식 셀 값을 찾아라.\n"
        "툴을 호출하며 단계별로 진행하고, 값을 찾으면 report_result를, "
        "찾지 못하면 report_not_found를 호출하라."
    )
    # period와 period_type을 분리 표기 — 합쳐서 주면 모델이 fetch_kosis_cell의
    # period 인자에 "M:2025-03"처럼 통째로 넣는 실수를 한다(실측).
    user = _claim_user_msg(claim)
    return {"role": "system", "content": system}, {"role": "user", "content": user}


# ── 루프: 단일 호출 (GPT 등 thinking+toolcall 동시 가능) ──────────────────────
def _loop_single(
    claim: Claim, preset: ModelPreset
) -> tuple[Evidence | None, int]:
    system, user = _build_messages(claim)
    messages: list[dict] = [system, user]
    total_tokens = 0
    cell_history: list[tuple[str, str, str]] = []

    for turn in range(_MAX_TURNS):
        resp = traced_chat(
            model_alias=preset.model_alias,
            model_name=preset.model_name,
            messages=messages,
            max_tokens=preset.max_tokens,
            temperature=preset.temperature,
            thinking_effort=preset.thinking_effort,
            tools=_TOOLS,
            tool_choice="auto",
            function_calling=True,
            trace_name=f"map_claim_via_agent:single:t{turn}",
        )
        total_tokens += resp.total_tokens or 0

        if not resp.tool_calls:
            break

        messages.append({
            "role": "assistant",
            "content": resp.text or "",
            "tool_calls": resp.tool_calls,
        })

        for tc in resp.tool_calls:
            fn = tc["function"]["name"]
            args = _parse_args(tc["function"].get("arguments", {}))

            if fn == "report_result":
                return _make_evidence(args, claim, cell_history), total_tokens
            if fn == "report_not_found":
                return None, total_tokens

            result = _exec_tool(fn, args, cell_history)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

    logger.warning("agent(single) max turns reached: claim=%s", claim.claim_id)
    return None, total_tokens


def _strip_tool_history(messages: list[dict]) -> list[dict]:
    """Think 단계용: tool_calls/tool 메시지를 제거 (thinking 모드와 충돌 방지).
    assistant tool_calls는 텍스트 요약으로 변환하되, 대응하는 tool 결과도 함께 포함한다.
    Think 모델이 이전 턴의 조회 결과(예: '값: 29028.5')를 보고 다음 전략을 올바르게 수정할 수 있다.
    """
    # tool_call_id → 결과 문자열 인덱스 구축
    tool_results: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id", "")
            tool_results[tc_id] = (msg.get("content") or "")[:150]

    result = []
    for msg in messages:
        if msg.get("role") == "tool":
            continue  # assistant 요약에 이미 포함
        tc_list = msg.get("toolCalls") or msg.get("tool_calls")
        if msg.get("role") == "assistant" and tc_list:
            summaries = []
            for tc in tc_list:
                fn = tc["function"]["name"]
                args = tc["function"].get("arguments", {})
                args_str = (
                    json.dumps(args, ensure_ascii=False)[:80]
                    if isinstance(args, dict) else str(args)[:80]
                )
                res = tool_results.get(tc.get("id", ""), "")
                res_str = f" → {res}" if res else ""
                summaries.append(f"{fn}({args_str}){res_str}")
            tc_text = "; ".join(summaries)
            content = (msg.get("content") or "") + (f"\n[툴 호출: {tc_text}]" if tc_text else "")
            result.append({"role": "assistant", "content": content})
        else:
            result.append(msg)
    return result


# ── 루프: Think→Act 분리 (HCX-007 등 동시 불가 모델) ────────────────────────
def _loop_split(
    claim: Claim,
    think_preset: ModelPreset,
    act_preset: ModelPreset,
) -> tuple[Evidence | None, int]:
    """매 턴: Think(THINK.md 자연어 분석) → Act(SKILL.md 도구 호출) → 반복.

    Think는 THINK.md 기반으로 자연어 전략만 출력 — JSON/코드 금지.
    Act는 SKILL.md 기반으로 실제 도구를 호출.
    """
    system, user = _build_messages(claim)
    messages: list[dict] = [system, user]
    total_tokens = 0
    cell_history: list[tuple[str, str, str]] = []

    for turn in range(_MAX_TURNS):
        # --- Think (SKILL.md 기반, 다음 단계 JSON 계획 출력) ---
        think_resp = traced_chat(
            model_alias=think_preset.model_alias,
            model_name=think_preset.model_name,
            messages=_strip_tool_history(messages),
            max_tokens=think_preset.max_tokens,
            temperature=think_preset.temperature,
            thinking_effort=think_preset.thinking_effort,
            trace_name=f"map_claim_via_agent:think:t{turn}",
        )
        total_tokens += think_resp.total_tokens or 0
        thought = think_resp.text or ""
        if not thought:
            break

        # ── 방향 B: Think JSON → Python 직접 실행 (Act 완전 제거) ─────────────
        # Think(HCX-007, thinking:low)가 JSON을 출력하면 Python이 직접 실행.
        # 자연어 출력 시 JSON 형식 재요청 1회 후 포기.
        try:
            plan = json.loads(thought.strip())
            if isinstance(plan, list) and plan and isinstance(plan[0], dict) and "name" in plan[0]:
                for step in plan:
                    fn = step.get("name", "")
                    args = step.get("arguments") or step.get("args") or {}
                    if not isinstance(args, dict):
                        args = {}

                    if fn == "report_result":
                        return _make_evidence(args, claim, cell_history), total_tokens
                    if fn == "report_not_found":
                        return None, total_tokens

                    result = _exec_tool(fn, args, cell_history)
                    args_str = json.dumps(args, ensure_ascii=False)[:80]
                    # 결과를 다음 Think에 전달 (tool-call 형식 아닌 일반 user 메시지)
                    messages.append({
                        "role": "user",
                        "content": f"조회결과: {fn} → {result[:300]}",
                    })
                continue  # 다음 Think 턴

        except (json.JSONDecodeError, TypeError, KeyError, AttributeError):
            pass

        # Think가 자연어를 출력한 경우 — JSON 형식 재요청 1회
        if turn < _MAX_TURNS - 1:
            messages.append({
                "role": "user",
                "content": (
                    f"[참고]\n{thought[:200]}\n\n"
                    "반드시 JSON 배열 형식으로만 응답하라:\n"
                    '[{"name": "툴이름", "arguments": {"인자": "값"}}]'
                ),
            })
        else:
            break

    logger.warning("agent(split) max turns reached: claim=%s", claim.claim_id)
    return None, total_tokens


# ── 디스패처 ──────────────────────────────────────────────────────────────────
def _run_agent(
    claim: Claim,
    think_preset: ModelPreset,
    act_preset: ModelPreset | None,
) -> tuple[Evidence | None, int]:
    """act_preset=None → 단일 호출(GPT 등), 지정 → Think→Act 분리(HCX 등)."""
    if act_preset is None:
        return _loop_single(claim, think_preset)
    return _loop_split(claim, think_preset, act_preset)


def _make_evidence(
    args: dict, claim: Claim, cell_history: list[tuple[str, str, str]]
) -> Evidence | None:
    # args가 dict가 아니면 처리 불가 (HCX가 JSON string으로 넘기는 경우 방어)
    if not isinstance(args, dict):
        return None

    # 1순위: report_result에 명시한 value (에이전트가 계산한 증감·변화율 포함)
    value: float | None = None
    try:
        value = float(args["value"])
    except (KeyError, TypeError, ValueError):
        pass

    # 2순위: 마지막 KOSIS 셀 조회값 (report_result value 누락 시 폴백)
    if value is None:
        for fn, _, res in reversed(cell_history):
            if fn == "fetch_kosis_cell" and res.startswith("값:"):
                try:
                    raw = res.split("값:")[1].strip().split()[0]  # 단위 표기 제거
                    value = float(raw)
                    break
                except (ValueError, IndexError):
                    pass

    if value is None:
        return None

    # evidence.unit: report_result args > cell_history 마지막 KOSIS 단위 > claim.unit
    # KOSIS 단위를 정확히 설정해야 7단계 compute_change의 unit 변환이 올바르게 동작한다.
    kosis_unit: str | None = None
    for fn, _, res in reversed(cell_history):
        if fn == "fetch_kosis_cell" and res.startswith("값:"):
            # "값: 29028.5 (단위: 천명)" 형태에서 단위 추출
            import re as _re
            m = _re.search(r"\(단위:\s*([^)]+)\)", res)
            if m:
                kosis_unit = m.group(1).strip()
            break

    unit = args.get("unit") or kosis_unit or claim.unit

    # org_id는 str 타입 필수 (에이전트가 int 101을 넘기는 경우 방어)
    org_id = args.get("org_id")
    if org_id is not None:
        org_id = str(org_id)

    return Evidence(
        claim_id=claim.claim_id,
        source="KOSIS",
        subject=claim.subject,
        unit=unit,
        period_type=claim.period_type,
        period=(lambda p: p[0] if isinstance(p, list) else p)(
            args.get("period") or claim.period_value.llm_value or ""
        ) or "",
        population=claim.population,
        value=value,
        kosis_org_id=org_id,
        kosis_tbl_id=args.get("tbl_id"),
        kosis_item_id=args.get("itm_id"),
    )


# ── 공개 인터페이스 ────────────────────────────────────────────────────────────
async def map_claim_via_agent(
    master_schema: MasterSchema,
    think_preset: ModelPreset = MAP_CLAIM_AGENT,
    act_preset: ModelPreset | None = None,
) -> None:
    """각 claim을 asyncio.gather로 병렬 실행. act_preset 지정 시 Think→Act 분리."""
    results = await asyncio.gather(
        *(
            asyncio.to_thread(_run_agent, claim, think_preset, act_preset)
            for claim in master_schema.claims
        )
    )

    analysis = []
    total_tok = 0
    for claim, (ev, tok) in zip(master_schema.claims, results):
        total_tok += tok
        analysis.append(ClaimAnalysis(
            claim_id=claim.claim_id,
            kosis_search=_empty_search(),
            kosis_query=_empty_query(ev.kosis_tbl_id or "" if ev else ""),
            evidences=[ev] if ev else [],
        ))

    master_schema.analysis = analysis
    if master_schema.article:
        logger.info("agent total_tokens=%d", total_tok)
