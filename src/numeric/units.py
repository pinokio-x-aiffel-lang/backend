"""단위 정렬 — evidence(KOSIS) 값을 claim 단위로 환산. [파이프라인 7]

src.kosis.units.convert_to_claim_unit 재사용. 단 '%p'(증감/포인트)은 절대값 '%'와
같은 그룹이지만 의미가 달라(변화량) 단일시점 ABSOLUTE 비교에서 분리한다.
"""
from __future__ import annotations

from src.kosis.units import convert_to_claim_unit

# 절대값 비교 부적격 단위(변화량/포인트). ABSOLUTE 경로에서 거른다.
_NON_ABSOLUTE_UNITS = {"%p", "%P", "%포인트", "포인트", "p"}


def align_value(
    kosis_value: float, kosis_unit: str, claim_unit: str
) -> tuple[float | None, str]:
    """evidence 값을 claim 단위로 환산. (값|None, 상태) 반환.

    상태: same_unit | ok | incompatible | unknown_unit | non_absolute
      - non_absolute: claim/kosis 단위가 %p 등 변화량이라 절대비교 부적격.
    """
    cu = (claim_unit or "").strip()
    ku = (kosis_unit or "").strip()
    if cu in _NON_ABSOLUTE_UNITS or ku in _NON_ABSOLUTE_UNITS:
        return None, "non_absolute"
    return convert_to_claim_unit(kosis_value, ku, cu)
