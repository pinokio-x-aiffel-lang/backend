"""KOSIS 응답 단위 ↔ claim 단위 변환.

KOSIS 는 표준 단위 (천달러/명/kg 등) 로 응답. 기사는 한국어 보도 관행
(만/억/조). 같은 dimensionality 그룹 안에서 multiplier 로 변환.

한계 (메모리 kosis-unit-conversion):
- `%p` vs `%` 같은 그룹에 있지만 의미적으로 다름. 별도 처리 필요.
- 지수 기준연도 (2020=100 vs 2015=100) — 현재 같은 그룹, 위험.
"""
from __future__ import annotations

import re

UNIT_GROUPS: list[dict[str, float]] = [
    # USD
    {"달러": 1, "천달러": 1_000, "백만달러": 1_000_000, "억달러": 100_000_000},
    # KRW (기사는 '만원' 표기도 흔하다 — KOSIS '만원' 응답과 매칭)
    {"원": 1, "만원": 10_000, "백만원": 1_000_000, "억원": 100_000_000, "조원": 1_000_000_000_000},
    # Count (KOSIS 고용/인구는 '천명' 으로 응답; 기사는 '명'·'만명')
    {"명": 1, "명 건": 1, "가구": 1, "개": 1, "천명": 1_000, "만명": 10_000, "천가구": 1_000, "만가구": 10_000},
    # Mass
    {"kg": 1, "g": 0.001, "톤": 1000},
    # Index
    {"지수": 1, "2020＝100": 1, "2020=100": 1},
    # 퍼센트 / 퍼센트포인트
    {"%": 1, "%p": 1},
]

# 단위 표기 표준화용 — 괄호류 제거. 전각 '＝'/공백은 _norm_unit 에서 함께 처리.
_PAREN_RE = re.compile(r"[()\[\]<>]")


def _norm_unit(unit: str) -> str:
    """단위 표기 표준화: 전각 '＝'→ASCII '=', 괄호류 제거, 앞뒤 공백 제거.

    표기만 다르고 같은 단위인 케이스를 흡수한다.
      예: '(2020=100)'·'2020＝100' → '2020=100' (같은 지수 단위).
    그룹 키도 같은 함수로 정규화해 비교하므로 사전 등록 표기에 의존하지 않는다.
    """
    return _PAREN_RE.sub("", (unit or "").strip().replace("＝", "="))


def find_unit_group(unit: str) -> dict[str, float] | None:
    nu = _norm_unit(unit)
    if not nu:
        return None
    for group in UNIT_GROUPS:
        if any(_norm_unit(key) == nu for key in group):
            return group
    return None


def _multiplier(group: dict[str, float], unit: str) -> float | None:
    """그룹에서 정규화 표기가 일치하는 키의 배수. 없으면 None."""
    nu = _norm_unit(unit)
    return next((mult for key, mult in group.items() if _norm_unit(key) == nu), None)


def convert_to_claim_unit(
    kosis_value: float, kosis_unit: str, claim_unit: str
) -> tuple[float | None, str]:
    """KOSIS 값을 claim 단위로 변환. (변환값, 상태) 반환.

    단위 표기는 _norm_unit 으로 표준화해 비교한다(전각 '＝'·괄호 차이 흡수).

    상태:
      'same_unit'    동일 단위, 변환 불필요
      'ok'           같은 그룹 내 변환 성공
      'incompatible' 다른 dimensionality (예: 명 vs 달러). NEI 트리거
      'unknown_unit' UNIT_GROUPS 에 없는 단위
    """
    if _norm_unit(kosis_unit) == _norm_unit(claim_unit):
        return kosis_value, "same_unit"
    g_claim = find_unit_group(claim_unit)
    g_kosis = find_unit_group(kosis_unit)
    if g_claim is None or g_kosis is None:
        return None, "unknown_unit"
    if g_claim is not g_kosis:
        return None, "incompatible"
    absolute = kosis_value * _multiplier(g_kosis, kosis_unit)
    return absolute / _multiplier(g_claim, claim_unit), "ok"
