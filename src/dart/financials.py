"""DART 재무 수치 조회 — 구조화 API + 감사보고서 원문 폴백.

상장사/주요 비상장사: fnlttSinglAcntAll.json 에 계정과목별 당기금액이 있다.
그 외 비상장 외감 법인: 위 API 가 status=013(없음) → 감사보고서 원문
(document.xml)을 받아 손익계산서 표에서 당기 금액을 best-effort 파싱한다.
(검증: '로쏘' corp_code=01070750, 2023 사업연도, 매출액=124,315,432,968)
"""
from __future__ import annotations

import re

from src.dart.accounts import resolve_account
from src.dart.client import DartError, call_dart, fetch_zip_xml
from src.dart.types import DartFact, DartQuery


def parse_won(raw: str) -> float | None:
    """DART 금액 문자열 → float. "(123)"=음수, "-"/빈값=None."""
    s = (raw or "").strip()
    if not s or s == "-":
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "")
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if neg else value


# --- 구조화 경로: fnlttSinglAcntAll ---------------------------------------

def find_account_row(rows: list[dict], account_nm: str, sj_div: str = "") -> dict | None:
    """매출 같은 개념을 XBRL account_id 우선, 라벨 별칭 보조로 매칭.

    라벨이 회사마다 달라도(매출액/영업수익) account_id(ifrs-full_Revenue)로 잡는다.
    id 매칭 row 를 별칭 매칭 row 보다 우선하고, sj_div 힌트가 있으면 그 안에서 우선.
    """
    ids, names = resolve_account(account_nm)
    id_hits = [r for r in rows if (r.get("account_id") or "").strip() in ids]
    name_hits = [r for r in rows if (r.get("account_nm") or "").strip() in names]
    seen = {id(r) for r in id_hits}
    candidates = id_hits + [r for r in name_hits if id(r) not in seen]
    if not candidates:
        return None
    if sj_div:
        for r in candidates:
            if (r.get("sj_div") or "") == sj_div:
                return r
    return candidates[0]


def fetch_structured_fact(corp_code: str, query: DartQuery, api_key: str) -> DartFact | None:
    """fnlttSinglAcntAll 에서 당기 금액 조회. 수록 대상 아니면(013) None."""
    fs_divs = [query.fs_div] + [d for d in ("OFS", "CFS") if d != query.fs_div]
    for fs_div in fs_divs:
        data = call_dart("fnlttSinglAcntAll.json", {
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bsns_year": query.bsns_year,
            "reprt_code": query.reprt_code,
            "fs_div": fs_div,
        })
        if data.get("status") == "013":
            continue
        row = find_account_row(data.get("list", []), query.account_nm, query.sj_div)
        if row is None:
            continue
        raw_amt = (row.get("thstrm_amount") or "").strip()
        value = parse_won(raw_amt)
        if value is None:
            raise DartError(f"당기금액 파싱 실패: {raw_amt!r}")
        return DartFact(
            corp_code=corp_code,
            corp_name=query.corp_name,
            account_nm=query.account_nm,
            bsns_year=query.bsns_year,
            value=value,
            value_raw=raw_amt,
            fs_div=fs_div,
            source="fnlttSinglAcntAll",
            period_label=(row.get("thstrm_nm") or "").strip() or None,
            raw=row,
        )
    return None


# --- 폴백 경로: 감사보고서 원문 --------------------------------------------

def search_disclosures(corp_code: str, bgn_de: str, end_de: str, api_key: str) -> list[dict]:
    """기간 내 공시 목록(list.json). 최신순. 없으면 빈 리스트."""
    data = call_dart("list.json", {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_count": "100",
        "sort": "date",
        "sort_mth": "desc",
    })
    if data.get("status") == "013":
        return []
    return data.get("list", [])


def pick_audit_report(disclosures: list[dict], bsns_year: str) -> dict | None:
    """감사보고서 중 사업연도가 보고서명에 든 최신 1건. 없으면 임의 감사보고서."""
    audits = [d for d in disclosures if "감사보고서" in (d.get("report_nm") or "")]
    for_year = [d for d in audits if bsns_year in (d.get("report_nm") or "")]
    pool = for_year or audits
    return pool[0] if pool else None


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _to_plain(doc_bytes: bytes) -> str:
    """원문 bytes → 태그 제거·공백 정규화 평문."""
    plain = re.sub(r"<[^>]+>", " ", _decode(doc_bytes))
    return re.sub(r"\s+", " ", plain)


# 천단위로 그룹된 금액만 인정 → 주석 열의 비그룹 숫자("21,26")는 배제. 괄호=음수.
_AMOUNT = r"-?\(?\d{1,3}(?:,\d{3})+\)?"

_UNIT_MULTIPLIERS = {"원": 1, "천원": 1_000, "백만원": 1_000_000, "십억원": 1_000_000_000}


def detect_unit_multiplier(doc_bytes: bytes, near: str | None = None) -> int:
    """'단위: 백만원' 등 → 금액 배율. 표기 없으면 1(원).

    near(금액 문자열)이 주어지면 그 위치 직전 가장 가까운 단위 표기를 쓴다 —
    문서에 단위가 섞일 때 정확하다(예: 본문=원, 주석=천원). near 가 없으면 전역 최빈.
    """
    plain = _to_plain(doc_bytes)
    units = [(m.start(), m.group(1))
             for m in re.finditer(r"단위\s*[:：]\s*(십억원|백만원|천원|원)", plain)]
    if not units:
        return 1
    pos = plain.find(near) if near else -1
    if pos >= 0:
        prior = [u for s, u in units if s < pos]
        unit = prior[-1] if prior else units[0][1]
    else:
        labels = [u for _, u in units]
        unit = max(set(labels), key=labels.count)
    return _UNIT_MULTIPLIERS.get(unit, 1)


def parse_income_statement_amount(doc_bytes: bytes, account_nm: str) -> tuple[str | None, str | None]:
    """감사보고서 원문에서 account_nm 의 당기(첫 번째) 금액을 best-effort 추출.

    손익계산서 표는 "과목 [주석] 당기 전기" 구조이고 당기가 왼쪽 금액열이다.
    라벨(긴 별칭 우선)을 찾은 뒤 그 뒤에서 '천단위로 그룹된 첫 금액'을 당기로 본다
    → 주석 열의 비그룹 숫자(예 "21,26")는 건너뛴다. (?<![가-힣])·(?![가-힣]) 로
    '제품매출액' 같은 합성어 오매칭을 피하고, 라벨 출현마다 인근 금액을 확인한다.
    단위 배율은 detect_unit_multiplier 로 별도 적용(여긴 원문 그대로 반환).
    한계: 표 구조가 비정형이면 빗나갈 수 있어 source(rcept_no)로 검증 권장.

    Returns: (당기 금액 원문, 기수 라벨 예 "제 23(당) 기") — 못 찾으면 (None, None).
    """
    plain = _to_plain(doc_bytes)
    _, names = resolve_account(account_nm)
    for label in sorted(names, key=len, reverse=True):
        for lm in re.finditer(rf"(?<![가-힣]){re.escape(label)}(?![가-힣])", plain):
            am = re.search(_AMOUNT, plain[lm.end():lm.end() + 60])
            if am:
                period = re.search(r"제\s*\d+\s*\(\s*당\s*\)\s*기", plain)
                return am.group(0), (period.group(0) if period else None)
    return None, None


def fetch_audit_report_fact(corp_code: str, query: DartQuery, api_key: str) -> DartFact | None:
    """감사보고서 원문에서 당기 금액 조회 (비상장 외감 폴백). 없으면 None.

    당기 사업연도(bsns_year)의 감사보고서는 이듬해 제출되므로
    [bsns_year .. bsns_year+1] 구간을 검색한다.
    """
    year = int(query.bsns_year)
    disclosures = search_disclosures(corp_code, f"{year}0101", f"{year + 1}1231", api_key)
    audit = pick_audit_report(disclosures, query.bsns_year)
    if audit is None:
        return None

    rcept_no = audit["rcept_no"]
    doc_bytes = fetch_zip_xml("document.xml", {"crtfc_key": api_key, "rcept_no": rcept_no})
    raw_amt, period_label = parse_income_statement_amount(doc_bytes, query.account_nm)
    value = parse_won(raw_amt) if raw_amt else None
    if value is None:
        return None
    value *= detect_unit_multiplier(doc_bytes, near=raw_amt)  # 금액 직전 단위(백만원 등) → 원
    return DartFact(
        corp_code=corp_code,
        corp_name=query.corp_name,
        account_nm=query.account_nm,
        bsns_year=query.bsns_year,
        value=value,
        value_raw=raw_amt,
        fs_div="AUDIT",
        source=rcept_no,
        period_label=period_label,
        raw=audit,
    )
