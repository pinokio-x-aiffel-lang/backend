"""DART 모듈 데이터 타입.

DartQuery: 한 통계 수치를 식별하는 입력. LLM retrieval funnel 결과
           (어느 기업·어느 사업연도·어느 계정과목인지).
DartFact:  공시에서 조회된 한 수치의 정규화된 표현 (Evidence 모듈 입력).
KOSIS 의 KosisQuery / KosisCell 과 평행한 역할.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DartQuery:
    """DART 수치 조회 입력.

    corp_name 으로 corp_code 를 해석한 뒤, bsns_year 사업연도의
    account_nm(예: "매출액") 당기 금액을 조회한다.

    reprt_code: 정기보고서 코드. 11011=사업, 11012=반기, 11013=1분기, 11014=3분기.
    fs_div:     OFS=재무제표(개별/별도), CFS=연결재무제표.
    sj_div:     찾을 재무제표 구분 힌트. IS=손익계산서, CIS=포괄손익,
                BS=재무상태표, CF=현금흐름. 빈 문자열이면 account_nm 만으로 매칭.
    """
    corp_name: str
    bsns_year: str
    account_nm: str
    reprt_code: str = "11011"
    fs_div: str = "OFS"
    sj_div: str = "IS"


@dataclass(frozen=True)
class DartFact:
    """공시 한 수치의 정규화된 표현.

    source 는 출처 추적용: 구조화 API 는 "fnlttSinglAcntAll",
    감사보고서 원문 폴백은 접수번호(rcept_no).
    fs_div 는 구조화 경로면 OFS/CFS, 원문 폴백이면 "AUDIT".
    """
    corp_code: str
    corp_name: str
    account_nm: str
    bsns_year: str
    value: float
    value_raw: str
    fs_div: str
    source: str
    period_label: str | None = None
    raw: dict = field(default_factory=dict)
