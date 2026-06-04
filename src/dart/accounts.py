"""계정과목 별칭/표준ID 해석.

같은 개념도 회사마다 라벨이 다르다(매출: 매출액/영업수익). fnlttSinglAcntAll 은
XBRL account_id 를 함께 주므로 표준 ID 매칭이 가장 견고하다.
(검증: 매출=ifrs-full_Revenue, 영업이익=dart_OperatingIncomeLoss,
 당기순이익=ifrs-full_ProfitLoss — 삼성전자·현대차·카카오·NAVER·셀트리온)

account_id 가 '-표준계정코드 미사용-' 인 회사나 감사보고서 원문(ID 없음)을 위해
라벨 별칭(aliases)도 함께 둔다. 새 지표는 _CONCEPTS 에 한 줄 추가.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

_logger = logging.getLogger("dart.accounts")


@dataclass(frozen=True)
class AccountConcept:
    """한 재무 개념의 표준 ID 집합과 라벨 별칭 집합."""
    key: str
    account_ids: frozenset[str]
    aliases: frozenset[str]


_CONCEPTS: tuple[AccountConcept, ...] = (
    AccountConcept(
        "매출",
        frozenset({"ifrs-full_Revenue"}),
        frozenset({"매출", "매출액", "영업수익", "수익(매출액)"}),
    ),
    AccountConcept(
        "영업이익",
        frozenset({"dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities"}),
        frozenset({"영업이익", "영업이익(손실)"}),
    ),
    AccountConcept(
        "당기순이익",
        frozenset({"ifrs-full_ProfitLoss"}),
        frozenset({"당기순이익", "당기순이익(손실)", "분기순이익", "반기순이익"}),
    ),
    # 금융사는 단일 '매출/영업수익' 표준계정이 없고 수익이 분해된다(이자/수수료/보험 등).
    # '매출'에 섞으면 오도되므로 별도 개념으로 둔다(KB금융·신한·하나 검증, 3사 id 일치).
    AccountConcept(
        "이자수익",
        frozenset({"ifrs-full_RevenueFromInterest"}),
        frozenset({"이자수익"}),
    ),
    AccountConcept(
        "수수료수익",
        frozenset({"ifrs-full_FeeAndCommissionIncome"}),
        frozenset({"수수료수익"}),
    ),
    # 재무상태표·현금흐름·주당지표 (삼성전자 OFS+CFS 검증).
    AccountConcept(
        "자산총계",
        frozenset({"ifrs-full_Assets"}),
        frozenset({"자산총계"}),
    ),
    AccountConcept(
        "부채총계",
        frozenset({"ifrs-full_Liabilities"}),
        frozenset({"부채총계"}),
    ),
    AccountConcept(
        "자본총계",
        frozenset({"ifrs-full_Equity"}),
        frozenset({"자본총계"}),
    ),
    AccountConcept(
        "영업활동현금흐름",
        frozenset({"ifrs-full_CashFlowsFromUsedInOperatingActivities"}),
        frozenset({"영업활동현금흐름", "영업활동으로인한현금흐름"}),
    ),
    AccountConcept(
        "기본주당이익",
        frozenset({"ifrs-full_BasicEarningsLossPerShare"}),
        frozenset({"기본주당이익", "기본주당이익(손실)", "주당순이익"}),
    ),
)


def resolve_account(account_nm: str) -> tuple[frozenset[str], frozenset[str]]:
    """account_nm 이 속한 개념의 (account_ids, aliases) 반환.

    개념의 key(예 "매출") 또는 별칭(예 "영업수익") 어디에 걸려도 같은 그룹 반환.
    어느 개념에도 없으면 (빈 ID, {자기 자신}) → 기존 정확 일치로 동작(후방호환).
    """
    target = account_nm.strip()
    for concept in _CONCEPTS:
        if target == concept.key or target in concept.aliases:
            return concept.account_ids, concept.aliases
    return frozenset(), frozenset({target})


def log_account_miss(account_nm: str, corp_name: str, bsns_year: str, available_names) -> None:
    """구조화 재무에 데이터는 있으나 account_nm 매칭이 실패했을 때 호출.

    사전 확장(_CONCEPTS 추가) 후보가 되도록 '사용 가능한 계정명'을 로그로 남긴다 —
    miss→log→add 루프의 'log' 단계('add'는 사람이 검토 후 수동, [[dart-module-design]]).
    """
    names = sorted({(n or "").strip() for n in available_names if n and n.strip()})
    _logger.warning(
        "DART 계정 매칭 실패(사전 확장 후보) | 요청=%r corp=%s year=%s | 사용가능 계정=%s",
        account_nm, corp_name, bsns_year, names[:40],
    )
