"""check_alignment.apply_alignment 단위 테스트 — 8단계 정합성 보정(순수).

대상은 7단계가 T(수치 일치)로 본 metric. 해석이 일치하면 T 유지, 오도/왜곡이면 M,
LLM 실패(judgment None)면 NEI + 근거 기록.
"""
from src.modules.check_alignment import AlignmentJudgment, apply_alignment
from src.schemas.runtime import MetricResult, MismatchType, Verdict


def _m(verdict=Verdict.TRUE):
    return MetricResult(operation="absolute", verdict=verdict)


def test_aligned_keeps_T():
    m = _m()
    apply_alignment(m, AlignmentJudgment(aligned=True, dimension=None, reason="주장 일치"))
    assert m.verdict is Verdict.TRUE and m.mismatch_type is None
    assert m.align_source == "llm" and m.align_reason == "주장 일치"


def test_misleading_to_M_with_dimension():
    m = _m()
    apply_alignment(
        m, AlignmentJudgment(aligned=False, dimension="population", reason="전체를 청년으로 단정")
    )
    assert m.verdict is Verdict.NEEDS_REVIEW
    assert m.mismatch_type is MismatchType.POPULATION
    assert m.align_source == "llm" and m.align_reason == "전체를 청년으로 단정"


def test_llm_failure_to_NEI_with_reason():
    m = _m()
    apply_alignment(m, None)
    assert m.verdict is Verdict.NOT_ENOUGH_INFO
    assert m.align_source == "llm_failed" and m.align_reason == "정합성 LLM 판정 실패"


def test_unknown_dimension_still_M():
    m = _m()
    apply_alignment(m, AlignmentJudgment(aligned=False, dimension="??", reason="왜곡"))
    assert m.verdict is Verdict.NEEDS_REVIEW  # 차원 매핑 실패해도 M
