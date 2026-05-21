"""KOSIS 응답 단위 ↔ claim 단위 변환.

KOSIS 는 표준 단위 (천달러/명/kg 등) 로 응답. 기사는 한국어 보도 관행
(만/억/조). 같은 dimensionality 그룹 안에서 multiplier 로 변환.

한계 (메모리 kosis-unit-conversion):
- `%p` vs `%` 같은 그룹에 있지만 의미적으로 다름. 별도 처리 필요.
- 지수 기준연도 (2020=100 vs 2015=100) — 현재 같은 그룹, 위험.
"""
from __future__ import annotations

UNIT_GROUPS: list[dict[str, float]] = [
    # USD
    {"달러": 1, "천달러": 1_000, "백만달러": 1_000_000, "억달러": 100_000_000},
    # KRW
    {"원": 1, "백만원": 1_000_000, "억원": 100_000_000, "조원": 1_000_000_000_000},
    # Count
    {"명": 1, "명 건": 1, "가구": 1, "개": 1},
    # Mass
    {"kg": 1, "g": 0.001, "톤": 1000},
    # Index
    {"지수": 1, "2020＝100": 1, "2020=100": 1},
    # 퍼센트 / 퍼센트포인트
    {"%": 1, "%p": 1},
]


def find_unit_group(unit: str) -> dict[str, float] | None:
    for group in UNIT_GROUPS:
        if unit in group:
            return group
    return None


def convert_to_claim_unit(
    kosis_value: float, kosis_unit: str, claim_unit: str
) -> tuple[float | None, str]:
    """KOSIS 값을 claim 단위로 변환. (변환값, 상태) 반환.

    상태:
      'same_unit'    동일 단위, 변환 불필요
      'ok'           같은 그룹 내 변환 성공
      'incompatible' 다른 dimensionality (예: 명 vs 달러). NEI 트리거
      'unknown_unit' UNIT_GROUPS 에 없는 단위
    """
    if kosis_unit == claim_unit:
        return kosis_value, "same_unit"
    g_claim = find_unit_group(claim_unit)
    g_kosis = find_unit_group(kosis_unit)
    if g_claim is None or g_kosis is None:
        return None, "unknown_unit"
    if g_claim is not g_kosis:
        return None, "incompatible"
    absolute = kosis_value * g_claim[kosis_unit]
    return absolute / g_claim[claim_unit], "ok"
