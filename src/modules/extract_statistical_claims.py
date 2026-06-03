from __future__ import annotations

import asyncio
import json

from src.llm.client import LlmError
from src.llm.llm_caller import LlmCaller
from src.schemas.runtime import Claim, MasterSchema, ValueSlot

_llm = LlmCaller()

_VALID_PERIOD_TYPES: frozenset[str] = frozenset({"Y", "M", "Q", "D"})


def _to_str(val: object, fallback: str = "불명") -> str:
    """LLM이 문자열 대신 리스트나 None을 반환할 때 안전하게 문자열로 변환."""
    if isinstance(val, list):
        return ", ".join(str(v) for v in val) if val else fallback
    return str(val) if val else fallback

_SYSTEM = (
    "뉴스 기사에서 수치 기반 통계 주장을 추출합니다.\n"
    "추출 대상: 통계청·연구기관·기업 실적 등 외부 출처에서 나온 수치, 시점이 명시된 경제·사회 지표.\n"
    "추출 제외: 제품 구성·사양, 단순 열거(~종, ~개 포함), 순위, 비율 없는 개수 나열.\n"
    "통계 주장이 없으면 {\"claims\": []} 를 반환하세요.\n"
    "마크다운 없이 순수 JSON만 출력하세요."
)

_USER_TMPL = """\
아래 기사에서 숫자가 포함된 문장을 찾아 검증 가능한 통계 주장을 최대 5개 추출하세요.

출력 형식 (JSON):
{{"claims":[
  {{
    "sentence": "원문 문장",
    "subject": "통계 주제",
    "value_raw": "수치 원문",
    "unit": "단위",
    "period_raw": "시점 원문",
    "period_type": "Y 또는 M 또는 Q 또는 D",
    "population": "대상 집단",
    "cited_source": "출처 (없으면 불명)"
  }}
]}}

기사:
{content}"""


class ExtractStatisticalClaimsError(Exception):
    """클레임 추출 실패 — LLM 응답 파싱 오류 등."""


async def extract_statistical_claims(record: MasterSchema) -> None:
    """
    [2] Extract Statistical Claims

    Input:
        record.article        # [1]에서 적재된 기사

    Output:
        record.claims         # list[Claim] (각 claim_id 부여)

    Responsibility:
        경량 LLM(HCX-003)으로 기사 본문에서 수치 기반 통계 주장을 추출해
        record.claims 에 채운다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    if not record.article:
        raise ExtractStatisticalClaimsError("record.article 이 없습니다.")

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _USER_TMPL.format(content=record.article.content)},
    ]

    try:
        response = await asyncio.to_thread(
            _llm.chat,
            "hyperclova",
            "HCX-007",
            messages,
            max_tokens=2048,
        )
    except LlmError as e:
        raise ExtractStatisticalClaimsError(f"LLM 호출 실패: {e}") from e

    try:
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0].strip()
        data = json.loads(text)
        raw_claims: list[dict] = data.get("claims", [])
    except json.JSONDecodeError as e:
        raise ExtractStatisticalClaimsError(f"LLM 응답 JSON 파싱 실패: {e}") from e

    claims: list[Claim] = []
    for idx, item in enumerate(raw_claims, start=1):
        period_type = item.get("period_type", "Y")
        if isinstance(period_type, list):
            period_type = period_type[0] if period_type else "Y"
        if period_type not in _VALID_PERIOD_TYPES:
            period_type = "Y"
        claims.append(
            Claim(
                claim_id=f"clm-{idx:04d}",
                article_id=record.article.article_id,
                sentence=_to_str(item.get("sentence"), ""),
                claim_type="수치",
                subject=_to_str(item.get("subject")),
                value=ValueSlot(raw=_to_str(item.get("value_raw")), llm_value="", is_inferred=False),
                unit=_to_str(item.get("unit")),
                aggregation="값",
                period_type=period_type,
                period_value=ValueSlot(raw=_to_str(item.get("period_raw")), llm_value="", is_inferred=False),
                compare_period_value=None,
                population=_to_str(item.get("population")),
                cited_source=_to_str(item.get("cited_source")),
            )
        )

    record.claims = claims
