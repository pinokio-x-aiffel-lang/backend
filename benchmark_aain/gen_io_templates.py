"""각 모듈 벤치 폴더(N_xxx)에 io.yml(계약)·io.jsonl(예시 I/O)을 생성.

- io.yml  : 모듈이 MasterSchema에서 '읽는 필드 / 쓰는 필드' 계약 명세 (사람용).
- io.jsonl: 그 단계의 input/expected MasterSchema 슬라이스 예시 1건.
           origin 소스 첫 레코드(취업자 수 2025-03)를 10단계에 이어지는 단일 예시로 사용.

스키마가 바뀌면 이 스크립트만 고쳐 재생성한다:  python3 benchmark_aain/gen_io_templates.py
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- #
# 10단계에 이어지는 단일 예시 (origin row_id=1: 취업자 수 2025-03)
# --------------------------------------------------------------------------- #
ARTICLE = {
    "article_id": "260614_row1",
    "title": "3월 취업자 수 2858만9000명…전년 동월 대비 19만3000명 증가",
    "content": "9일 통계청이 발표한 ‘3월 고용동향’에 따르면, 지난 3월 취업자 수는 "
               "2858만9000명으로 전년 동월 대비 19만3000명 증가했다.",
    "published_at": "2025-04-09",
    "source": "연합뉴스",
    "url": None,
}

SENTENCE = "지난 3월 취업자 수는 2858만9000명으로 전년 동월 대비 19만3000명 증가했다."

CLAIM_RAW = {
    "claim_id": "c1",
    "article_id": "260614_row1",
    "sentence": SENTENCE,
    "claim_type": "absolute",
    "subject": "취업자 수",
    "value": {"raw": "2858만9000명", "llm_value": "", "is_inferred": False},
    "unit": "명",
    "aggregation": "sum",
    "period_type": "M",
    "period_value": {"raw": "지난 3월", "llm_value": "", "is_inferred": False},
    "compare_period_value": {"raw": "전년 동월", "llm_value": "", "is_inferred": False},
    "compare_conquer": None,
    "population": "전체",
    "cited_source": "통계청 3월 고용동향",
}

CLAIM_NORM = json.loads(json.dumps(CLAIM_RAW))
CLAIM_NORM["value"]["llm_value"] = "28589000"
CLAIM_NORM["period_value"]["llm_value"] = "2025-03"
CLAIM_NORM["compare_period_value"]["llm_value"] = "2024-03"

KOSIS_SEARCH = {
    "api": "statisticsSearch.do",
    "query": "취업자 수 월",
    "params": "searchNm=취업자+수&...",
    "hits": 12,
    "selected_tbl_id": "DT_1DA7001S",
    "selected_tbl_name": "취업자 (월)",
    "success": 1,
    "error_msg": None,
    "duration_ms": 480,
}

CANDIDATE = {
    "org_id": "101",
    "tbl_id": "DT_1DA7001S",
    "tbl_nm": "취업자 (월)",
    "org_nm": "통계청",
    "stat_nm": "경제활동인구조사",
    "prd_de": "201301~202503",
}

KOSIS_QUERY = {
    "api": "statisticsData.do",
    "tbl_id": "DT_1DA7001S",
    "params": "itmId=T20&prdSe=M&...",
    "rows_returned": 1,
    "success": 1,
    "error_msg": None,
    "duration_ms": 530,
}

EVIDENCE = {
    "claim_id": "c1",
    "source": "KOSIS",
    "subject": "취업자 수",
    "unit": "명",
    "period_type": "M",
    "period": "2025-03",
    "population": "전체",
    "evidence_id": "DT_1DA7001S:T20:2025-03",
    "value": 28589000.0,
    "kosis_org_id": "101",
    "kosis_tbl_id": "DT_1DA7001S",
    "table_name": "취업자 (월)",
    "kosis_item_id": "T20",
    "url": "https://kosis.kr/...",
    "classification": {},
    "last_updated": "2025-04-09",
    "retrieved_at": "2026-06-18T00:00:00",
    "compare_value": 28396000.0,
    "compare_period": "2024-03",
    "population_fallback": False,
    "match_source": "rule",
}

CELL_ATTEMPT = {
    "tbl_id": "DT_1DA7001S",
    "tbl_nm": "취업자 (월)",
    "matched": True,
    "value": 28589000.0,
    "unit": "명",
    "itm_id": "T20",
    "items": ["취업자", "실업자", "경제활동인구"],
    "axes": {"성별": ["계", "남자", "여자"]},
    "population_fallback": False,
    "match_source": "rule",
    "error": None,
}

METRIC_T7 = {
    "operation": "absolute",
    "claim_value": 28589000.0,
    "kosis_value": 28589000.0,
    "rel_diff": 0.0,
    "within_tolerance": True,
    "verdict": "T",
    "mismatch_type": None,
    "note": None,
    "align_reason": None,
    "align_source": None,
    "compare_id": None,
    "computed_value": None,
}

METRIC_T8 = json.loads(json.dumps(METRIC_T7))
METRIC_T8["align_reason"] = "주어(취업자 수)·기간(2025-03)·모집단(전체) 모두 일치"
METRIC_T8["align_source"] = "llm"

CLAIM_RESULT_SEED = {
    "claim_id": "c1",
    "verdict": "UNVERIFIED",
    "claim_value": "28589000",
    "kosis_value": "28589000",
    "metric": METRIC_T7,
    "needs_hitl": False,
}

CLAIM_RESULT_FINAL = {
    "claim_id": "c1",
    "verdict": "T",
    "verdict_human": "사실",
    "mismatch_type": None,
    "claim_value": "28589000",
    "kosis_value": "28589000",
    "explanation": "주장한 2858만9000명은 KOSIS 취업자(월) 2025-03 공식 수치와 일치한다.",
    "confidence": 1.0,
    "metric": METRIC_T8,
}

SUMMARY = {
    "total_claims": 1,
    "verdict_counts": {"T": 1, "F": 0, "M": 0, "N": 0},
    "overall_confidence": 1.0,
    "coverage": 1.0,
    "overall_opinion": "",
}

SUMMARY_FINAL = json.loads(json.dumps(SUMMARY))
SUMMARY_FINAL["overall_opinion"] = "기사의 핵심 수치는 통계청 공식 수치와 일치한다."

# --------------------------------------------------------------------------- #
# 단계별 계약 + 예시 I/O 슬라이스
# --------------------------------------------------------------------------- #
STAGES = [
    {
        "n": 1, "folder": "1_article", "module": "load_article",
        "title": "기사 내용 확인",
        "desc": "content(URL 또는 본문 텍스트)를 Article 로 변환한다.",
        "reads": [("content", "str | None", "기사 URL 또는 본문 텍스트 (원본 입력)")],
        "writes": [("article", "Article", "원문 기사 메타데이터(article_id/title/content/published_at/source/url)")],
        "input": {"content": ARTICLE["content"]},
        "expected": {"article": ARTICLE},
    },
    {
        "n": 2, "folder": "2_claim", "module": "extract_statistical_claims",
        "title": "클레임 추출",
        "desc": "기사 본문을 원자 문장으로 쪼개 수치 기반 Claim 을 추출한다(claim_type=NONE 포함).",
        "reads": [("article", "Article", "[1]에서 적재된 기사")],
        "writes": [
            ("sentences", "list[str]", "필터·원자화된 검증 단위 문장"),
            ("claims", "list[Claim]", "추출된 수치 주장 (value.llm_value 는 아직 빈값)"),
        ],
        "input": {"article": ARTICLE},
        "expected": {"sentences": [SENTENCE], "claims": [CLAIM_RAW]},
    },
    {
        "n": 3, "folder": "3_normalize", "module": "normalize_claim",
        "title": "한국어 수사 산술로 변환",
        "desc": "claims[*].value.raw(한국어 수사·기간)를 산술/표준형으로 정규화해 llm_value 에 채운다.",
        "reads": [("claims[*].value.raw", "str", "한국어 수사 표현(예: 2858만9000명, 지난 3월)")],
        "writes": [("claims[*].value.llm_value", "str", "정규화된 산술/표준형(예: 28589000, 2025-03)")],
        "input": {"claims": [CLAIM_RAW]},
        "expected": {"claims": [CLAIM_NORM]},
    },
    {
        "n": 4, "folder": "4_retrieve", "module": "retrieve_kosis_candidates",
        "title": "KOSIS 통계표 n개 찾기",
        "desc": "claim 의 subject/unit/period 로 KOSIS 통합검색을 돌려 후보 통계표 풀을 만든다.",
        "reads": [("claims", "list[Claim]", "subject/unit/period 등 검색 키")],
        "writes": [("analysis", "list[ClaimAnalysis]", "claim별 kosis_search 로그 + candidates 풀")],
        "input": {"claims": [CLAIM_NORM]},
        "expected": {"analysis": [{
            "claim_id": "c1",
            "kosis_search": KOSIS_SEARCH,
            "candidates": [CANDIDATE],
        }]},
    },
    {
        "n": 5, "folder": "5_fetch", "module": "fetch_kosis_data",
        "title": "KOSIS 셀 값 조회",
        "desc": "후보 표별로 항목/분류축을 매칭해 셀 값을 조회하고 매칭된 셀을 evidences 로 적재한다.",
        "reads": [
            ("claims", "list[Claim]", "subject/population/period 매칭 기준"),
            ("analysis[*].candidates", "list[KosisCandidate]", "[4] 후보 표 풀"),
        ],
        "writes": [
            ("analysis[*].kosis_query", "KosisQuery", "statisticsData 호출 로그"),
            ("analysis[*].cell_attempts", "list[CellAttempt]", "후보 표별 매칭 시도(디버깅)"),
            ("analysis[*].evidences", "list[Evidence]", "매칭된 셀(RANK 순)"),
        ],
        "input": {"claims": [CLAIM_NORM], "analysis": [{"claim_id": "c1", "candidates": [CANDIDATE]}]},
        "expected": {"analysis": [{
            "claim_id": "c1",
            "kosis_query": KOSIS_QUERY,
            "cell_attempts": [CELL_ATTEMPT],
            "evidences": [EVIDENCE],
        }]},
    },
    {
        "n": 6, "folder": "6_rank", "module": "rank_evidence",
        "title": "증거 랭킹",
        "desc": "claim 적합도로 evidences 를 재정렬해 1위 적합 표를 evidences[0] 으로 둔다.",
        "reads": [("analysis[*].evidences", "list[Evidence]", "[5]가 내보낸 매칭 표 n개(RANK 순)")],
        "writes": [("analysis[*].evidences", "list[Evidence]", "재정렬됨 — evidences[0] = 최적 표")],
        "input": {"analysis": [{"claim_id": "c1", "evidences": [EVIDENCE]}]},
        "expected": {"analysis": [{"claim_id": "c1", "evidences": [EVIDENCE]}]},
    },
    {
        "n": 7, "folder": "7_metric", "module": "calculate_metric",
        "title": "통계 수치 비교 판단",
        "desc": "정규화된 주장 수치와 KOSIS 공식 수치(evidences[0])를 비교해 MetricResult 를 만든다(verdict T/F/NEI 초기).",
        "reads": [
            ("claims[*].value.llm_value", "str", "정규화된 주장 수치"),
            ("analysis[*].evidences", "list[Evidence]", "KOSIS 공식 수치(선정 셀)"),
        ],
        "writes": [
            ("verifications", "Verifications", "생성 — claim_results 스켈레톤 + summary"),
            ("verifications.claim_results[*].metric", "MetricResult", "비교 결과(verdict 초기값)"),
        ],
        "input": {"claims": [CLAIM_NORM], "analysis": [{"claim_id": "c1", "evidences": [EVIDENCE]}]},
        "expected": {"verifications": {"summary": SUMMARY, "claim_results": [CLAIM_RESULT_SEED]}},
    },
    {
        "n": 8, "folder": "8_alignment", "module": "check_alignment",
        "title": "통계수치와 문장의 정합성 판단",
        "desc": "verdict=T 인 건만 문장 해석 정합성을 LLM 으로 재판정한다(일치→T, 오도/왜곡→M, LLM실패→NEI).",
        "reads": [("verifications.claim_results[*].metric", "MetricResult", "[7] verdict=T 결과")],
        "writes": [("verifications.claim_results[*].metric", "MetricResult", "보정 — verdict(T→T/M/NEI) + align_reason/align_source")],
        "input": {"verifications": {"summary": SUMMARY, "claim_results": [CLAIM_RESULT_SEED]}},
        "expected": {"verifications": {"summary": SUMMARY, "claim_results": [
            {"claim_id": "c1", "metric": METRIC_T8}]}},
    },
    {
        "n": 9, "folder": "9_verdict", "module": "decide_verdict",
        "title": "종합 분석·검증 결과 생성",
        "desc": "metric 으로 claim별 verdict/mismatch_type 을 확정하고 기사 단위 summary(분포·신뢰도·coverage)를 채운다.",
        "reads": [("verifications.claim_results[*].metric", "MetricResult", "[7]~[8] 비교·정합성 결과")],
        "writes": [
            ("verifications.claim_results[*].verdict", "str", "확정 판정(T/F/M/N)"),
            ("verifications.summary", "VerificationSummary", "verdict_counts·overall_confidence·coverage"),
        ],
        "input": {"verifications": {"summary": SUMMARY, "claim_results": [
            {"claim_id": "c1", "metric": METRIC_T8}]}},
        "expected": {"verifications": {"summary": SUMMARY, "claim_results": [
            {"claim_id": "c1", "verdict": "T", "mismatch_type": None, "metric": METRIC_T8}]}},
    },
    {
        "n": 10, "folder": "10_explanation", "module": "generate_explanation",
        "title": "설명 생성",
        "desc": "claim별 설명과 기사 단위 종합 의견(overall_opinion)을 생성한다(LLM 실패 시 템플릿 폴백).",
        "reads": [
            ("verifications", "Verifications", "[9] 확정 판정 결과"),
            ("claims", "list[Claim]", "subject/unit/period 참조"),
        ],
        "writes": [
            ("verifications.claim_results[*].explanation", "str", "claim별 설명"),
            ("verifications.summary.overall_opinion", "str", "기사 단위 LLM 종합 의견"),
        ],
        "input": {
            "verifications": {"summary": SUMMARY, "claim_results": [
                {"claim_id": "c1", "verdict": "T", "metric": METRIC_T8}]},
            "claims": [CLAIM_NORM],
        },
        "expected": {"verifications": {"summary": SUMMARY_FINAL, "claim_results": [CLAIM_RESULT_FINAL]}},
    },
]


def emit_yaml(s: dict) -> str:
    def js(v):  # json.dumps → YAML 호환 더블쿼트 스칼라 (| : 등 안전)
        return json.dumps(v, ensure_ascii=False)

    lines = [
        f"module: {s['module']}",
        f"step: {s['n']}",
        f"folder: {js(s['folder'])}",
        f"title: {js(s['title'])}",
        f"description: {js(s['desc'])}",
        "reads:",
    ]
    for field, typ, desc in s["reads"]:
        lines += [f"  - field: {js(field)}", f"    type: {js(typ)}", f"    desc: {js(desc)}"]
    lines.append("writes:")
    for field, typ, desc in s["writes"]:
        lines += [f"  - field: {js(field)}", f"    type: {js(typ)}", f"    desc: {js(desc)}"]
    return "\n".join(lines) + "\n"


def main() -> None:
    for s in STAGES:
        folder = BASE / s["folder"]
        folder.mkdir(exist_ok=True)
        (folder / "io.yml").write_text(emit_yaml(s), encoding="utf-8")
        record = {"input": s["input"], "expected": s["expected"]}
        (folder / "io.jsonl").write_text(
            json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"  {s['folder']}/io.yml, io.jsonl")
    print(f"done: {len(STAGES)} folders")


if __name__ == "__main__":
    main()
