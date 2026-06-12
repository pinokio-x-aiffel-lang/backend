"""src/metaphor 단위 테스트 — 사전 로더 + 비유비교 매핑."""
from __future__ import annotations

import pytest

from src.metaphor import find_metaphors, load_entries, map_metaphor

# ── loader ────────────────────────────────────────────────────────────────────


def test_load_default_dictionary():
    entries = load_entries()
    by_id = {e.id: e for e in entries}
    yeouido = by_id["yeouido_area"]
    assert yeouido.value == 2.9
    assert yeouido.unit == "km2"
    assert "여의도" in yeouido.aliases


def test_duplicate_alias_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
entries:
  - {id: a, name: A, aliases: [같은별칭], category: area, value: 1, unit: km2}
  - {id: b, name: B, aliases: [같은별칭], category: area, value: 2, unit: km2}
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="중복 alias"):
        load_entries(bad)


def test_missing_field_rejected(tmp_path):
    bad = tmp_path / "missing.yaml"
    bad.write_text(
        "entries:\n  - {id: a, name: A, aliases: [엑스], category: area, value: 1}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="필수 필드 누락"):
        load_entries(bad)


def test_nonpositive_value_rejected(tmp_path):
    bad = tmp_path / "zero.yaml"
    bad.write_text(
        "entries:\n  - {id: a, name: A, aliases: [엑스], category: area, value: 0, unit: km2}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="양수"):
        load_entries(bad)


# ── mapper: 배수 패턴 ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "entry_id", "multiplier", "resolved", "unit"),
    [
        # N배 (숫자)
        ("공장 부지는 여의도 면적의 3배에 이른다", "yeouido_area", 3.0, 8.7, "km2"),
        ("매립지는 여의도의 1.5배 규모다", "yeouido_area", 1.5, 4.35, "km2"),
        ("63빌딩 높이의 2배에 달하는 구조물", "building63_height", 2.0, 500.0, "m"),
        # N배 (고유어 수사)
        ("남산 높이의 세 배에 이르는", "namsan_height", 3.0, 795.0, "m"),
        # 수량사 (개·바퀴)
        ("신축 단지는 축구장 70개 규모다", "soccer_field_area", 70.0, 499800.0, "m2"),
        ("케이블 총 길이는 지구 두 바퀴에 달한다", "earth_circumference", 2.0, 80150.0, "km"),
        ("지구 한 바퀴 반에 이르는 거리", "earth_circumference", 1.5, 60112.5, "km"),
        ("올림픽 수영장 10개 분량의 물", "olympic_pool_volume", 10.0, 25000.0, "m3"),
        # 분수·절반
        ("여의도 면적의 3분의 1 수준", "yeouido_area", 1 / 3, round(2.9 / 3, 6), "km2"),
        ("서울시 면적의 절반에 해당하는", "seoul_area", 0.5, 302.6, "km2"),
        # 동급 표현 (=1배)
        ("여의도 면적과 맞먹는 규모", "yeouido_area", 1.0, 2.9, "km2"),
        ("여의도만 한 크기의 빙하", "yeouido_area", 1.0, 2.9, "km2"),
        # "배 반" = +0.5
        ("여의도 면적의 3배 반에 이르는", "yeouido_area", 3.5, 10.15, "km2"),
    ],
)
def test_map_metaphor(text, entry_id, multiplier, resolved, unit):
    m = map_metaphor(text)
    assert m is not None, f"매칭 실패: {text}"
    assert m.entry.id == entry_id
    assert m.multiplier == pytest.approx(multiplier)
    assert m.resolved_value == pytest.approx(resolved)
    assert m.unit == unit


# ── mapper: 오탐 방지 ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "여의도 증권가에서 열린 행사",            # 배수 표현 없는 지명 언급
        "성남산업단지의 2배 규모",               # 합성어 내부 '남산' — 단어 경계로 차단
        "여의도동의 3배",                       # '여의도동'은 행정동 명칭 — 연결어 불일치
        "비유 표현이 전혀 없는 문장",
    ],
)
def test_no_false_positive(text):
    assert find_metaphors(text) == []


# ── mapper: 복수 매칭 ─────────────────────────────────────────────────────────


def test_multiple_matches_in_order():
    text = "부지는 여의도 면적의 2배, 건물 연면적은 축구장 100개 규모다"
    found = find_metaphors(text)
    assert [m.entry.id for m in found] == ["yeouido_area", "soccer_field_area"]
    assert found[0].resolved_value == pytest.approx(5.8)
    assert found[1].resolved_value == pytest.approx(714000.0)
