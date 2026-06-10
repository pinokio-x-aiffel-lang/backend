"""일회성 수동 테스트 — extract_statistical_claims 단일 문장 실행."""
import asyncio

from src.llm.llm_caller import LlmCaller
from src.modules.extract_statistical_claims import _SYSTEM, _USER_TMPL, extract_statistical_claims
from src.schemas.runtime import Article, MasterSchema

_SENTENCE = (
    "2018년 출시 후 2019년 한 해 동안 4만대 넘게 팔렸던 렉스턴 스포츠는 "
    "지난해 판매량이 1만2779대에 그쳤고, 2020년 5000대 이상을 판매했던 "
    "콜로라도도 지난해에는 368대에 머물렀다."
)


async def debug_raw() -> None:
    """raw response 확인."""
    llm = LlmCaller()
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _USER_TMPL.format(content=_SENTENCE)},
    ]
    response = await asyncio.to_thread(llm.chat, "hyperclova", "HCX-007", messages, max_tokens=2048)
    print("=== RAW RESPONSE ===")
    print(repr(response.text))
    print("====================\n")


async def main() -> None:
    record = MasterSchema(
        article=Article(
            article_id="art-manual-001",
            title="띠부씰 테스트",
            content=_SENTENCE,
            published_at="2024-01-01",
            source="수동테스트",
        )
    )

    await extract_statistical_claims(record)

    import json as _json
    with open("scripts/extract_result.json", "w", encoding="utf-8") as f:
        _json.dump([c.model_dump() for c in record.claims], f, ensure_ascii=False, indent=2)
    print(f"추출된 클레임 수: {len(record.claims)} → scripts/extract_result.json 저장됨\n")
    for claim in record.claims:
        print(f"[{claim.claim_id}]")
        print(f"  claim_id               : {claim.claim_id}")
        print(f"  article_id             : {claim.article_id}")
        print(f"  sentence               : {claim.sentence}")
        print(f"  claim_type             : {claim.claim_type}")
        print(f"  subject                : {claim.subject}")
        print(f"  value.raw              : {claim.value.raw}")
        print(f"  value.llm_value        : {claim.value.llm_value!r}")
        print(f"  value.is_inferred      : {claim.value.is_inferred}")
        print(f"  unit                   : {claim.unit}")
        print(f"  aggregation            : {claim.aggregation}")
        print(f"  period_type            : {claim.period_type}")
        print(f"  period_value.raw       : {claim.period_value.raw}")
        print(f"  period_value.llm_value : {claim.period_value.llm_value!r}")
        print(f"  period_value.is_inferred: {claim.period_value.is_inferred}")
        print(f"  compare_period_value   : {claim.compare_period_value}")
        print(f"  population             : {claim.population}")
        print(f"  cited_source           : {claim.cited_source}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
