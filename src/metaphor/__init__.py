"""비유비교 사전·매핑 — "여의도 면적의 3배" 류 표현을 실수치로 환산.

사전 데이터는 metaphor.yaml, 로딩은 loader, 매칭·환산은 mapper.
"""
from src.metaphor.loader import MetaphorEntry, load_entries
from src.metaphor.mapper import MetaphorMatch, find_metaphors, map_metaphor

__all__ = [
    "MetaphorEntry",
    "MetaphorMatch",
    "find_metaphors",
    "load_entries",
    "map_metaphor",
]
