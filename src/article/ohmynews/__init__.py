"""오마이뉴스(ohmynews.com) 전용 추출 패키지.

공개 API:
    is_ohmynews(url)        # 오마이뉴스 기사 URL 판별
    extract_content(tree)   # 사진 캡션·[편집자말] 제거한 본문 복구
    extract_meta(tree)      # 매체명 한글화(og:site_name 'ohmynews' → '오마이뉴스')
"""
from src.article.ohmynews.extractor import extract_content, extract_meta, is_ohmynews

__all__ = ["extract_content", "extract_meta", "is_ohmynews"]
