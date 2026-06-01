from __future__ import annotations

from src.schemas.runtime import Article, MasterSchema


class LoadArticleError(Exception):
    """기사 적재 실패 — URL 오류·크롤링/파싱 실패 등."""


async def load_article(record: MasterSchema) -> None:
    """
    [1] Article Load

    Input:
        record.content        # 기사 URL 또는 본문 텍스트

    Output:
        record.article

    Responsibility:
        content(URL 또는 본문)를 Article 로 변환해 record.article 에 저장한다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # TODO: 실제 구현 — content(URL/본문) 크롤링·파싱. 현재는 happy-path 더미.
    record.article = Article(
        article_id="art-0001",
        title="(더미) 기사 제목",
        content=record.content or "",
        published_at="2024-01-01",
        source="(더미) 출처",
    )
