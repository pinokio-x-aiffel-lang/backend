"""extract_statistical_claims 임시 테스트 스크립트."""
import asyncio
import json

from src.schemas.runtime import Article, MasterSchema
from src.modules.extract_statistical_claims import extract_statistical_claims

CONTENT = """\
통계청에 따르면 지난달 한국 근로자의 주당 평균 근로시간은 38.8시간이다. 맥킨지는 노동시장 참여율을 높이는 것도 방법이라고 했다. 이 중 고령 인구가 노동시장에 남는 비율, 즉 '근로 수명'을 높이는 것도 고려해야 한다는 것이다. 일본의 경우 65세 이상 노동시장 참여율(26%)이 프랑스(4%) 등을 앞서고 있으며, 이는 일본의 1997년 이후 연평균 노동생산성 증가율(1.1%)이 서유럽(0.8%)을 앞설 수 있던 요인이 됐다고 했다. 하지만 맥킨지는 일본 방식도 한계는 있다고 봤다. 일본의 경우 25~64세는 주당 평균 30시간을 일하지만, 65세 이상은 7시간 일하는 것으로 집계돼 결국 고령화에 따른 노동시간 감소는 피할 수 없기 때문이다.\
"""

async def main() -> None:
    ms = MasterSchema(
        article=Article(
            article_id="test-001",
            title="노동시간 테스트",
            content=CONTENT,
        )
    )
    await extract_statistical_claims(ms)

    print(f"\n총 {len(ms.claims)}개 claim 추출\n")
    for c in ms.claims:
        print(f"[{c.claim_id}] claim_type={c.claim_type.value}")
        print(f"  sentence : {c.sentence}")
        print(f"  subject  : {c.subject}")
        print(f"  value    : {c.value.raw}")
        print(f"  unit     : {c.unit}")
        print(f"  period   : {c.period_value.raw} ({c.period_type})")
        print(f"  source   : {c.cited_source}")
        print()

if __name__ == "__main__":
    asyncio.run(main())
