"""뉴스타파(newstapa.org) 전용 추출 패키지.

공개 API:
    is_newstapa(url)        # 뉴스타파 기사 URL 판별
    extract_content(tree)   # Editor.js 본문 블록(소제목·문단) 수집
    extract_meta(tree)      # 게시일·매체명(표준 메타에 없음) 보강
"""
from src.article.newstapa.extractor import extract_content, extract_meta, is_newstapa

__all__ = ["extract_content", "extract_meta", "is_newstapa"]
