"""Pipeline — 단계 조립·실행, 이벤트 스트리밍.

단계 함수: _article_parse ~ _verdict
  - (ctx: PipelineContext) -> PipelineContext 시그니처
  - 각 함수가 ctx의 해당 필드를 채우고 반환
  - 구현 준비되면 raise NotImplementedError를 실제 로직으로 교체

Pipeline.run():
  - 단계 함수들을 순서대로 실행
  - 각 단계 시작/완료/오류를 StepEvent로 yield
  - 전 단계 완료 후 ResultEvent yield
  - HTTP / SSE / Queue 등 전송 방식은 모름 → 호출자(verify_service)의 몫
"""
from __future__ import annotations

import time
from collections.abc import AsyncGenerator

from src.pipeline.context import PipelineContext
from src.pipeline.events import PipelineEvent, ResultEvent, StepEvent


# ── 단계 함수들 ──────────────────────────────────────────────────────────────

async def _article_parse(ctx: PipelineContext) -> PipelineContext:
    # TODO: URL 판별 → 크롤링 / 본문 직접 입력 처리
    #       article_id 생성, ctx.article 채우기
    raise NotImplementedError


async def _claim_extract(ctx: PipelineContext) -> PipelineContext:
    # TODO: LLM(HCX)으로 수치 기반 주장 추출
    #       ctx.claims 채우기 (Claim 스키마, claim_id 부여)
    raise NotImplementedError


async def _kosis_search(ctx: PipelineContext) -> PipelineContext:
    # TODO: claim별 subject+unit → KOSIS statisticsSearch.do
    #       가장 적합한 테이블 선정, ctx.analysis 초기화
    raise NotImplementedError


async def _kosis_query(ctx: PipelineContext) -> PipelineContext:
    # TODO: 선정 테이블에서 period/population 맞는 행 조회
    #       src.kosis.fetch_cell 사용, ctx.analysis[*].evidence 채우기
    raise NotImplementedError


async def _normalize(ctx: PipelineContext) -> PipelineContext:
    # TODO: "약 23만" → 230000, "전년" → 2023 등 한국어 수치 정규화
    #       src.numeric 활용, claim.value.llm_value 갱신
    raise NotImplementedError


async def _compare(ctx: PipelineContext) -> PipelineContext:
    # TODO: claim 수치(llm_value) vs KOSIS evidence.value 수치 비교
    #       verdict / mismatch_type 초기 판정
    raise NotImplementedError


async def _coherence(ctx: PipelineContext) -> PipelineContext:
    # TODO: 수치 비교만으로 판단 어려운 케이스 LLM 재판정
    #       단위 불일치·집계 방식 차이 등 모호 케이스 처리
    raise NotImplementedError


async def _synthesize(ctx: PipelineContext) -> PipelineContext:
    # TODO: 전체 claim verdict 종합 → overall_verdict, average_confidence
    raise NotImplementedError


async def _explain(ctx: PipelineContext) -> PipelineContext:
    # TODO: verdict + 수치 차이 → 한국어 자연어 설명 (LLM)
    #       ctx.analysis[*].verification.explanation 채우기
    raise NotImplementedError


async def _verdict(ctx: PipelineContext) -> PipelineContext:
    # TODO: analysis 데이터를 Verifications 스키마로 조립
    #       ctx.verifications 채우기
    raise NotImplementedError


# ── 단계 목록 (순서 고정) ─────────────────────────────────────────────────────

_STEPS = [
    ("기사 내용 확인",                _article_parse),
    ("클레임 추출",                   _claim_extract),
    ("KOSIS 통계표 찾기",             _kosis_search),
    ("KOSIS 조회",                    _kosis_query),
    ("한국어 수사 산술로 변환",        _normalize),
    ("통계 수치 비교 판단",            _compare),
    ("통계수치와 문장의 정합성 판단",  _coherence),
    ("종합 분석",                     _synthesize),
    ("설명 생각",                     _explain),
    ("검증 결과 생성",                _verdict),
]


# ── Pipeline ─────────────────────────────────────────────────────────────────

class Pipeline:
    async def run(self, content: str) -> AsyncGenerator[PipelineEvent, None]:
        ctx = PipelineContext(content=content)

        for i, (name, fn) in enumerate(_STEPS, 1):
            t0 = time.monotonic()
            yield StepEvent(step=i, name=name, status="running")

            try:
                ctx = await fn(ctx)
            except Exception as e:
                yield StepEvent(
                    step=i, name=name, status="error",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    error=str(e),
                )
                raise

            yield StepEvent(
                step=i, name=name, status="done",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        yield ResultEvent(context=ctx)
