"""아시아경제(asiae.co.kr) 전용 추출 패키지.

공개 API:
    is_asiae(url)               # 아시아경제 기사 URL 판별
    extract_content(tree)       # #txt_area 본문 문단 복구(캡션·광고·관련기사 제외)
"""
from src.article.asiae.extractor import extract_content, is_asiae

__all__ = ["extract_content", "is_asiae"]
