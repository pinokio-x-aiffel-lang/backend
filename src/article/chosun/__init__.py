"""조선일보(Arc/Fusion) 전용 추출 패키지.

공개 API:
    is_chosun(url)              # 조선일보(Arc/Fusion) URL 판별
    extract_content(page_html)  # window.Fusion content_elements 에서 본문 복구
"""
from src.article.chosun.extractor import extract_content, is_chosun

__all__ = ["extract_content", "is_chosun"]
