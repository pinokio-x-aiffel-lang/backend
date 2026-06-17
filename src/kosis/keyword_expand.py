"""subject → KOSIS 검색 키워드 변형 생성 (결정적 룰).

[4] retrieve_kosis_candidates 가 단일 키워드 대신 여러 변형으로 검색해 recall 을
올리도록, subject 에서 {원본·핵심명사·동의어·상위어} 변형을 만든다. 전부 결정적이라
재현 가능하다(LLM 폴백은 retrieve 모듈이 별도로 얹는다).

설계:
  - variants[0] == 기존 전처리 키워드(_normalize) → 확장이 비어도 베이스라인과 동일.
  - 괄호·단위·수량어 제거, 선행 수식어(청년층·고령 등) 분리, 동의어 치환.
  - 호출 증폭 방지를 위해 호출부가 MAX_VARIANTS 로 자른다(여기선 dedup 만).
"""
from __future__ import annotations

import re

# subject 앞 국가 한정어 — KOSIS 키워드 오염 (retrieve 와 동일 규칙).
_DROP_PREFIXES = ("한국 ", "한국의 ", "우리나라 ", "우리나라의 ")

# 선행 수식어(인구집단·범위 한정) — 떼면 상위 표명에 매칭될 여지.
_LEAD_MODIFIERS = (
    "청년층", "청년", "고령자", "고령", "노인", "전체", "국내", "국민",
    "15~29세", "15세 이상", "20대", "30대", "40대", "50대", "60대",
)

# 동의어·상위어 치환(KOSIS 표명 어휘에 맞춤). key 가 subject 에 포함되면 치환본 추가.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "쌀": ("양곡",),
    "가계신용": ("가계부채",),
    "집값": ("주택가격", "주택매매가격"),
    "아파트 가격": ("아파트 매매가격", "주택가격"),
    "물가": ("소비자물가지수",),
    "근로자": ("취업자",),
    "임금": ("근로소득", "임금근로"),
    "소매판매": ("소매판매액지수",),
    "출생아": ("출생",),
    "혼인 건수": ("혼인",),
    "사망자": ("사망",),
    "자살률": ("고의적 자해", "자살"),
}

# 괄호류 (…)/[…]/<…> 와 그 안 내용.
_PAREN_RE = re.compile(r"[\(\[\<][^\)\]\>]*[\)\]\>]")
# 수량·단위 토큰(예: "10개", "8송이", "1인당").
_QUANTITY_RE = re.compile(r"\b\d+\s*(개|송이|명|건|원|대|마리|톤|kg|g)\b|1인당")


def _normalize(subject: str) -> str:
    """기존 retrieve 전처리와 동일: 국가 접두어 제거 + 공백 제거."""
    s = subject.strip()
    for p in _DROP_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
            break
    return "".join(s.split())


def _strip_noise(subject: str) -> str:
    """괄호·수량어·평균 등 검색 노이즈 제거(공백은 유지 — 토큰 변형용)."""
    s = _PAREN_RE.sub(" ", subject)
    s = _QUANTITY_RE.sub(" ", s)
    s = s.replace("평균", " ")
    return re.sub(r"\s+", " ", s).strip()


def _drop_lead_modifier(subject: str) -> str | None:
    """선행 인구집단 수식어를 떼고 남은 핵심(없으면 None)."""
    s = subject.strip()
    for m in _LEAD_MODIFIERS:
        if s.startswith(m) and len(s) > len(m):
            return s[len(m):].strip()
    return None


def _apply_synonyms(subject: str) -> list[str]:
    """subject 에 동의어 key 가 있으면 치환본들 생성."""
    out: list[str] = []
    for key, alts in _SYNONYMS.items():
        if key in subject:
            out.extend(subject.replace(key, alt) for alt in alts)
    return out


def expand_subject(subject: str, *, max_variants: int = 5) -> list[str]:
    """subject → 검색 키워드 변형 리스트(결정적). [0]=기존 전처리 키워드.

    빈 subject → []. 변형은 dedup·순서보존, max_variants 로 절단.
    """
    if not subject or not subject.strip():
        return []

    raw: list[str] = []
    raw.append(_normalize(subject))                  # [0] 베이스라인 키워드

    cleaned = _strip_noise(subject)                  # 괄호·수량어 제거본
    if cleaned and cleaned != subject:
        raw.append(_normalize(cleaned))

    for src in (subject, cleaned):                   # 수식어 분리본
        core = _drop_lead_modifier(src)
        if core:
            raw.append(_normalize(core))

    for src in (subject, cleaned):                   # 동의어 치환본
        for syn in _apply_synonyms(src):
            raw.append(_normalize(syn))

    # dedup(순서보존) + 빈 문자열 제거 + 절단
    seen: set[str] = set()
    out: list[str] = []
    for kw in raw:
        if kw and kw not in seen:
            seen.add(kw)
            out.append(kw)
        if len(out) >= max_variants:
            break
    return out
