import type { VerifyResponse } from '@/lib/api/schema'
import { VerdictBadge } from '@/components/verdict/VerdictBadge'
import { ClaimCard } from '@/components/claim/ClaimCard'
import { KosisTableCard } from '@/components/evidence/KosisTableCard'
import { NumericComparison } from '@/components/evidence/NumericComparison'
import { ExplanationPanel } from '@/components/explanation/ExplanationPanel'
import { PipelineProgress } from '@/components/pipeline/PipelineProgress'
import { formatDate } from '@/lib/format'

interface ResultLayoutProps {
  result: VerifyResponse
  onReset: () => void
}

export function ResultLayout({ result, onReset }: ResultLayoutProps) {
  return (
    <div className="w-full space-y-6">
      {/* Article info bar */}
      <div
        className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-sm pb-4 border-b"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <div>
          {result.article.title && (
            <p className="font-semibold" style={{ color: 'var(--color-text-primary)' }}>
              {result.article.title}
            </p>
          )}
          <p
            className="font-mono text-xs truncate max-w-xl"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            {result.article.url}
          </p>
          {result.article.published_at && (
            <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
              {formatDate(result.article.published_at)} 발행
            </p>
          )}
        </div>
        <button
          onClick={onReset}
          className="text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors shrink-0 self-start sm:self-auto"
          style={{
            color: 'var(--color-accent)',
            background: 'var(--color-accent-subtle)',
          }}
          aria-label="새 URL로 다시 검증하기"
        >
          새 기사 검증
        </button>
      </div>

      {/* Verdict */}
      <VerdictBadge verdict={result.verdict} confidence={result.confidence} />

      {/* Bento grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <ClaimCard claim={result.claim} />
        </div>
        <div>
          {result.evidence ? (
            <KosisTableCard evidence={result.evidence} />
          ) : (
            <div
              className="rounded-xl p-6 h-full flex items-center justify-center text-center"
              style={{
                border: '2px dashed var(--color-border)',
                color: 'var(--color-text-tertiary)',
              }}
            >
              <div>
                <div className="text-3xl mb-2" aria-hidden="true">○</div>
                <p className="text-sm font-medium">매칭 통계표 없음</p>
                <p className="text-xs mt-1">KOSIS 카탈로그에서 대응 표를 찾지 못했습니다</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {result.comparison && (
        <NumericComparison comparison={result.comparison} />
      )}

      <ExplanationPanel explanation={result.explanation} />

      {/* Pipeline detail */}
      <div
        className="rounded-xl p-5 border"
        style={{
          background: 'var(--color-surface-subtle)',
          borderColor: 'var(--color-border-subtle)',
        }}
      >
        <h3
          className="text-xs font-bold uppercase tracking-widest mb-4"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          파이프라인 실행 내역
        </h3>
        <PipelineProgress currentStep={9} finalSteps={result.pipeline} />
      </div>
    </div>
  )
}
