"""네이버 뉴스 전용 추출 패키지.

공개 API:
    is_naver(url)                     # 네이버 기사 URL 판별
    extract_meta(url, tree, page_html)  # title·published_at·source 추출(+자가복구)
"""
from src.article.naver.extractor import extract_meta, is_naver

__all__ = ["extract_meta", "is_naver"]
