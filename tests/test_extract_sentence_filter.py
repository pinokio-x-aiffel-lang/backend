"""extract_statistical_claims 의 규칙 기반 전단계 테스트.

[a] 문장 필터(_filter_stat_candidates)와 preprocess 공개 API(clean_and_split)만 검증.
LLM 을 쓰는 [b] 원자화·[c] 추출은 통합 테스트(tests/results) 대상.
"""
from __future__ import annotations

from src.modules.extract_statistical_claims import _filter_stat_candidates
from src.modules.preprocess_article import clean_and_split


# ── _filter_stat_candidates ──────────────────────────────────────────────────

def test_keeps_sentences_with_digits():
    sents = [
        "지난해 실업률이 3.2%에서 2.7%로 하락했다.",
        "정부는 고용 회복세가 뚜렷하다고 평가했다.",
    ]
    assert _filter_stat_candidates(sents) == [sents[0]]


def test_keeps_korean_percent_and_point():
    sents = [
        "물가상승률이 두 퍼센트를 넘었다.",
        "금리가 0.5포인트 올랐다.",
        "전문가들은 신중한 입장이다.",
    ]
    assert _filter_stat_candidates(sents) == sents[:2]


def test_keeps_metaphoric_numeric_expressions():
    sents = [
        "물가가 두 배 뛰었다는 체감이다.",
        "거래량이 반토막 났다.",
        "수출이 절반 수준으로 줄었다.",
        "분위기가 한층 좋아졌다.",
    ]
    assert _filter_stat_candidates(sents) == sents[:3]


def test_drops_all_when_no_numeric():
    sents = ["좋은 아침입니다.", "내일은 맑겠습니다."]
    assert _filter_stat_candidates(sents) == []


# ── clean_and_split ──────────────────────────────────────────────────────────

def test_clean_and_split_removes_noise_and_splits():
    content = (
        "<p>지난해 실업률이 3.2%에서 2.7%로 하락했다. 정부는 고용 회복세가"
        " 뚜렷하다고 평가했다.&nbsp;</p>\n"
        "◆ 수출액은 5,231억 달러를 기록했다.\n"
        "홍길동 기자 hong@news.com ⓒ뉴스사 무단전재 금지\n"
    )
    sentences = clean_and_split(content)
    assert "지난해 실업률이 3.2%에서 2.7%로 하락했다" in sentences[0]
    assert any("수출액은 5,231억 달러" in s for s in sentences)
    joined = " ".join(sentences)
    assert "<p>" not in joined
    assert "기자" not in joined
    assert "hong@news.com" not in joined
