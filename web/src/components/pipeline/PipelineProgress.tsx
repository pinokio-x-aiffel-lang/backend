import type { PipelineStep } from '@/lib/api/schema'
import { useReducedMotion } from '@/hooks/useReducedMotion'

const STEP_NAMES = [
  '기사 추출',
  '주장 탐지',
  '주장 분류',
  '주장 구조화',
  'KOSIS 필터',
  '임베딩 검색',
  '재순위화',
  'RAG 추론',
  'API + 비교',
]

interface PipelineProgressProps {
  currentStep: number
  finalSteps?: PipelineStep[]
}

export function PipelineProgress({ currentStep, finalSteps }: PipelineProgressProps) {
  const reducedMotion = useReducedMotion()

  const getStepStatus = (idx: number): 'done' | 'running' | 'pending' | 'error' | 'skipped' => {
    if (finalSteps) {
      return finalSteps[idx]?.status ?? 'done'
    }
    if (idx < currentStep) return 'done'
    if (idx === currentStep) return 'running'
    return 'pending'
  }

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`검증 진행 중: ${currentStep}/9단계 완료`}
      className="w-full"
    >
      <div className="flex items-start justify-between gap-1 mb-4 overflow-x-auto pb-2">
        {STEP_NAMES.map((name, idx) => {
          const status = getStepStatus(idx)
          const isActive = status === 'running'
          const isDone = status === 'done'
          const isError = status === 'error'
          const isSkipped = status === 'skipped'

          return (
            <div key={idx} className="flex flex-col items-center gap-1.5 min-w-[56px]">
              {/* Connector line */}
              <div className="flex items-center w-full">
                {idx > 0 && (
                  <div
                    className="h-px flex-1 transition-all"
                    style={{
                      background: isDone || isError
                        ? (isError ? 'var(--color-verdict-false)' : 'var(--color-verdict-true)')
                        : 'var(--color-border)',
                      transitionDuration: 'var(--duration-normal)',
                    }}
                  />
                )}
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-all ${isActive && !reducedMotion ? 'animate-pulse' : ''}`}
                  style={{
                    background: isDone
                      ? 'var(--color-verdict-true)'
                      : isError
                        ? 'var(--color-verdict-false)'
                        : isActive
                          ? 'var(--color-accent)'
                          : isSkipped
                            ? 'var(--color-border)'
                            : 'var(--color-surface-subtle)',
                    color: isDone || isError || isActive ? 'white' : 'var(--color-text-tertiary)',
                    boxShadow: isActive ? '0 0 0 3px var(--color-accent-subtle)' : 'none',
                    transitionDuration: 'var(--duration-normal)',
                  }}
                  aria-hidden="true"
                >
                  {isDone ? '✓' : isError ? '✕' : isSkipped ? '−' : idx + 1}
                </div>
                {idx < STEP_NAMES.length - 1 && (
                  <div
                    className="h-px flex-1 transition-all"
                    style={{
                      background: isDone
                        ? 'var(--color-verdict-true)'
                        : 'var(--color-border)',
                      transitionDuration: 'var(--duration-normal)',
                    }}
                  />
                )}
              </div>
              <span
                className="text-center leading-tight"
                style={{
                  fontSize: 'var(--text-xs)',
                  color: isActive
                    ? 'var(--color-accent)'
                    : isDone
                      ? 'var(--color-text-secondary)'
                      : 'var(--color-text-tertiary)',
                  fontWeight: isActive ? 700 : 400,
                }}
              >
                {name}
              </span>
            </div>
          )
        })}
      </div>

      {!finalSteps && (
        <p
          className="text-center text-sm"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          {currentStep < 9
            ? `${STEP_NAMES[currentStep] ?? ''} 처리 중...`
            : '완료 대기 중...'}
        </p>
      )}
    </div>
  )
}
