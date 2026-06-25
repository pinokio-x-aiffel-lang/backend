"""파이프라인 단계별 LLM 호출 프리셋 (provider·model·파라미터 묶음).

각 단계가 모델/파라미터를 리터럴로 하드코딩하지 않고 여기서 가져다 쓴다.
한곳에 모아 "어느 단계가 어느 모델을 어떤 파라미터로" 쓰는지 일원 검토·변경.

역할 경계:
  - 모델 능력/메타(context_window, max_output_tokens, thinking 지원 등)는
    `src/llm/provider.py` 가 보유 — 여기 중복 금지.
  - 이 파일은 단계별 "선택 정책"만 둔다.

사용:
    from src.llm.model_presets import EXTRACT_CLAIMS as P
    _llm.chat(P.model_alias, P.model_name, messages, max_tokens=P.max_tokens)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPreset:
    """한 단계의 LLM 호출 설정. `LlmCaller.chat` 인자에 1:1 대응."""

    model_alias: str             # provider alias (예: "hyperclova")
    model_name: str              # 모델명 (예: "HCX-007")
    max_tokens: int
    temperature: float | None = None


# ── 파이프라인 단계별 프리셋 ──────────────────────────────────────────────────

# 기사 전처리 (preprocess_article)
PREPROCESS = ModelPreset(
    model_alias="hyperclova",
    model_name="HCX-005",
    max_tokens=1024,
)

# 통계 주장 추출 (extract_statistical_claims)
# 결정적 추출·평가 재현성을 위해 temperature 0 고정.
EXTRACT_CLAIMS = ModelPreset(
    model_alias="hyperclova",
    model_name="HCX-007",
    max_tokens=2048,
    temperature=0.0,
)

# 네이버 셀렉터 자동 복구 (src/article/naver/repair.py)
# 레이아웃 변경 감지 시 축약 HTML 을 주고 바뀐 요소의 셀렉터를 찾게 한다.
# 결정론적 추출이 필요하므로 temperature 를 낮게 둔다.
NAVER_SELECTOR_REPAIR = ModelPreset(
    model_alias="hyperclova",
    model_name="HCX-007",
    max_tokens=1024,
    temperature=0.1,
)

# 수치 정규화 LLM 폴백 (normalize_claim)
NORMALIZE_VALUE = ModelPreset(
    model_alias="hyperclova",
    model_name="HCX-005",
    max_tokens=64,
    temperature=0.0,
)

# 시점 정규화 LLM 폴백 (normalize_claim)
NORMALIZE_PERIOD = ModelPreset(
    model_alias="hyperclova",
    model_name="HCX-005",
    max_tokens=32,
    temperature=0.0,
)

# KOSIS 분류축 값 매칭 LLM 폴백 (fetch_kosis_data → resolve 의 population→objL 코드)
# 규칙+동의어 매칭이 실패할 때만 호출한다. 주어진 보기(코드 목록) 중 하나를 고르는
# 닫힌 선택 문제라 저토큰·저온도. structured outputs 가 필요해 HCX-007.
RESOLVE_AXIS_MATCH = ModelPreset(
    model_alias="hyperclova",
    model_name="HCX-007",
    max_tokens=128,
    temperature=0.0,
)

# KOSIS 검색 키워드 확장 LLM 폴백 ([4] retrieve_kosis_candidates)
# 룰 사전이 변형을 못 만들 때만 호출. subject → KOSIS 표명 어휘의 검색어 몇 개를
# 자유 생성(동의어·상위어). 짧은 목록이라 저토큰. structured outputs(JSON) → HCX-007.
EXPAND_KEYWORDS = ModelPreset(
    model_alias="hyperclova",
    model_name="HCX-007",
    max_tokens=128,
    temperature=0.0,
)

# 증거 표 리랭킹 ([6] rank_evidence)
# 후보 표들(표명·항목·분류축; 값 제외) 중 주장에 가장 적합한 표 1위를 고른다.
# 닫힌 선택(보기 중 하나)이라 저토큰·저온도. structured outputs 필요 → HCX-007.
RANK_EVIDENCE = ModelPreset(
    model_alias="hyperclova",
    model_name="HCX-007",
    max_tokens=128,
    temperature=0.0,
)

# 정합성 재판정 ([8] check_alignment)
# 주장 vs KOSIS 증거가 '같은 대상·방식 측정'인지 판정(structured outputs). 모호(M)
# 케이스에만 호출하는 닫힌 판정이라 저토큰·저온도. structured 필요 → HCX-007.
CHECK_ALIGNMENT = ModelPreset(
    model_alias="hyperclova",
    model_name="HCX-007",
    max_tokens=256,
    temperature=0.0,
)

# 기사 단위 종합 의견 ([10] generate_explanation)
# claim별 검증 결과 요약을 받아 기사 전체 총평을 한 문단으로 자유 서술(structured 불필요).
# 자연스러운 한국어 문단 생성이라 HCX-005·넉넉한 토큰. 약간의 유창함을 위해 저온도(0).
# 보다는 살짝 높여 0.3. 실패 시 호출부가 결정적 템플릿 총평으로 폴백한다.
GENERATE_OPINION = ModelPreset(
    model_alias="hyperclova",
    model_name="HCX-005",
    max_tokens=512,
    temperature=0.3,
)
