"""모집단(claim.population) ↔ KOSIS 분류축 값 표기 동의어 — 도메인 데이터.

claim 은 '청년'처럼 말하지만 통계표 분류축은 '15~29세'로 적어 직접 매칭이 안 되는
갭(case C)을 메운다. resolve._match_code 가 이 사전으로 후보를 확장한다.

동치 그룹으로 정의한다: 한 그룹 안의 표현들은 서로 같은 대상을 가리킨다. 그룹에서
'멤버 → 같은 그룹의 나머지' lookup(SYNONYMS)을 자동 생성하므로, 개념을 그룹당 한 번만
적으면 된다(예전 dict 의 '청년↔청년층' 양방향 수기 중복 제거). 표기는 raw 로 두고,
대시·물결·공백 차이는 resolve._norm 이 비교 시점에 흡수한다(여기서 정규화 안 함).

그룹은 tuple(순서 보존)이라 lookup 순서가 결정적이다 — resolve 의 결정성 유지.
새 모집단 표현이 필요하면 해당 그룹에 추가하거나 그룹을 새로 만든다.
"""
from __future__ import annotations

# 같은 대상을 가리키는 표현들의 동치 그룹. 첫 원소는 보통 claim 이 쓰는 대표어,
# 뒤에 통계표 축값 표기를 둔다(순서는 매칭 후보 시도 순서에만 영향).
POPULATION_SYNONYM_GROUPS: list[tuple[str, ...]] = [
    ("청년", "청년층", "15~29세"),
    ("고령", "고령자", "고령인구", "노인", "고령층", "65세이상"),
    ("유소년", "0~14세", "14세이하"),
    ("생산가능인구", "근로연령인구", "15~64세"),
    ("남성", "남자"),
    ("여성", "여자"),
    # 국가축(국제 비교표)은 한국을 '대한민국'으로 적는다. claim 의 '한국/전국/우리나라'를
    # 거기에 잇는다. 국내표는 '전국/한국'이 먼저 정확매칭되니 무해(대한민국은 fallback).
    ("한국", "대한민국", "우리나라", "남한", "전국"),
]

# 멤버 → 같은 그룹의 나머지 멤버들. resolve._expand 가 이 형태로 소비한다.
SYNONYMS: dict[str, list[str]] = {
    member: [other for other in group if other != member]
    for group in POPULATION_SYNONYM_GROUPS
    for member in group
}
