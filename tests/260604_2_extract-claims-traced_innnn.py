"""extract_statistical_claims 모듈 수동 테스트 + Langfuse 트레이싱.

실행:
    infisical run --env dev --path /LangFuse -- uv run python tests/260604_2_extract-claims-traced_innnn.py

Langfuse 대시보드에서 'test-extract-statistical-claims' trace 확인.

대상 모듈: extract_statistical_claims (+ Langfuse 트레이싱)
작성자: innnn <innnn712@gmail.com>
작성일: 2026-06-04
"""
from __future__ import annotations

import asyncio

from langfuse import get_client

from src.modules.extract_statistical_claims import extract_statistical_claims
from src.schemas.runtime import Article, MasterSchema

_ARTICLE = """\
여당이 지방 미분양 주택에 대한 DSR 규제를 한시적으로 완화하라고 금융당국에 압박을 넣고 있다.
금융당국은 가계부채 관리를 위해 정책 기조를 유지하며 신중한 입장을 보이고 있다.
국민의힘이 경제분야 민생대책 점검 당정협의회에서 수도권을 제외한 지역의 미분양 주택에 대한 DSR 규제 완화를 요청했다.
DSR은 개인이 주택 구매를 위해 받은 대출의 연간 원리금 상환액을 연소득으로 나눈 비율이다.
이는 주택 구입자가 감당할 수 있을 만큼만 대출을 받도록 유도하기 위한 소득 심사 지표다.
전통적인 DTI와는 달리, DSR은 주택담보대출 외의 다른 모든 대출의 원금 및 이자 상환액을 포함한다.
DSR 심사 기준은 40% 이하로 설정되어 있어, DTI의 60%보다 엄격하다.
원리금 계산 시에는 실제 은행 대출 금리가 아닌 금융당국이 지정한 '스트레스 금리'를 사용한다.
여당은 악성 미분양을 겪는 지역의 문제를 해결하기 위해 DSR 규제 완화를 주장하고 있으나, 금융위는 명확한 답변을 회피하고 있다.
금융위는 DSR 한시적 완화에 대해 신중하게 접근하겠다고 밝혔다.
금융위의 고민 중 하나는 DSR 완화의 실효성에 관한 것이다.
대부분의 저가 주택 구입자들은 이미 DSR을 적용받지 않는 정부 지원 대출 상품을 이용 중이다.
대구시의 미분양 주택 수는 2674가구이며, 평균 아파트 가격은 약 3억4121만원이다.
경북과 전남에서도 많은 미분양 주택이 있으며, 각각의 평균 아파트 가격은 1억9236만원, 1억9281만원이다.
DSR 규제 완화는 주로 고가의 지방 주택을 시중은행 대출로 구매하려는 사람들에게 혜택이 돌아갈 가능성이 크다.
엄격한 대출 규제가 일부 미분양의 원인이 될 수 있다는 의견도 있다.
수도권 외곽 지역의 주택 구매자들은 정책 모기지 이용 시 DTI 심사조차 받지 않는다.
따라서 소득 심사 문제로 인해 미분양이 증가했다고 단정짓기는 어렵다.
지난해 말 기준, 전국의 준공 후 미분양 주택은 2만1480가구로 집계되었으며 이는 전월 대비 15.2% 증가한 수치이다.
준공 후 미분양 물량은 2023년 8월 이후 17개월 연속 증가하고 있다.
"""


async def main() -> None:
    lf = get_client()

    with lf.start_as_current_observation(
        type="trace",
        name="test-extract-statistical-claims",
    ):
        record = MasterSchema(
            article=Article(
                article_id="test-trace-001",
                title="DSR 규제 완화 논의",
                content=_ARTICLE,
                published_at="2025-01-01",
                source="테스트",
            ),
            sentences=_ARTICLE.strip().splitlines(),
        )

        print("extract_statistical_claims 호출 중...")
        await extract_statistical_claims(record)

    print(f"\n추출된 클레임: {len(record.claims)}개\n")
    for claim in record.claims:
        print(
            f"  [{claim.claim_id}] detailed_type={claim.claim_type} / {claim.detailed_type}"
        )
        print(f"          sentence  : {claim.sentence[:60]}...")
        print(f"          value_raw : {claim.value.raw}  unit={claim.unit}")
        print(f"          period    : {claim.period_value.raw} ({claim.period_type})")
        print(f"          compared_id: {claim.compared_id}")
        print()

    lf.flush()
    print("Langfuse 트레이싱 완료 — 대시보드에서 'test-extract-statistical-claims' trace 확인.")


if __name__ == "__main__":
    asyncio.run(main())
