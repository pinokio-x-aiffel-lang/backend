"""numeric.value.parse_claim_value 단위 테스트 — value.llm_value 형식 분기."""
from src.numeric.value import ValueKind, parse_claim_value


def test_scalar():
    p = parse_claim_value("38.8")
    assert p.kind is ValueKind.SCALAR and p.number == 38.8


def test_signed_positive_and_negative():
    pos = parse_claim_value("+3.0")
    assert pos.kind is ValueKind.SIGNED and pos.number == 3.0
    neg = parse_claim_value("-5.0")
    assert neg.kind is ValueKind.SIGNED and neg.number == -5.0


def test_range_forms():
    assert parse_claim_value("50~100").kind is ValueKind.RANGE
    assert parse_claim_value(">=5").kind is ValueKind.RANGE
    assert parse_claim_value("<10").kind is ValueKind.RANGE


def test_ratio():
    assert parse_claim_value("3:2").kind is ValueKind.RATIO


def test_bare_sign():
    assert parse_claim_value("+").kind is ValueKind.BARE_SIGN
    assert parse_claim_value("-").kind is ValueKind.BARE_SIGN


def test_comma_scalar():
    p = parse_claim_value("1,234.5")
    assert p.kind is ValueKind.SCALAR and p.number == 1234.5


def test_unparsable():
    assert parse_claim_value("약 절반").kind is ValueKind.UNPARSABLE
    assert parse_claim_value("").kind is ValueKind.UNPARSABLE
