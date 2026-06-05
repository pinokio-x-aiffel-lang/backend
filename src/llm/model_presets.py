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
EXTRACT_CLAIMS = ModelPreset(
    model_alias="hyperclova",
    model_name="HCX-007",
    max_tokens=2048,
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
