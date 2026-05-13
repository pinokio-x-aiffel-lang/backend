import { getVerdictMeta } from '@/lib/verdict'
import type { Verdict } from '@/lib/api/schema'
import { useReducedMotion } from '@/hooks/useReducedMotion'

interface VerdictBadgeProps {
  verdict: Verdict
  confidence: number
}

export function VerdictBadge({ verdict, confidence }: VerdictBadgeProps) {
  const meta = getVerdictMeta(verdict)
  const reducedMotion = useReducedMotion()

  return (
    <div
      className={`rounded-2xl p-6 md:p-8 flex flex-col md:flex-row items-start md:items-center gap-6 ${!reducedMotion ? 'transition-all' : ''}`}
      style={{
        background: `var(${meta.bgVar})`,
        border: `2px solid var(${meta.borderVar})`,
      }}
    >
      {/* Verdict label */}
      <div className="flex flex-col gap-1">
        <div
          className="font-black tracking-tight leading-none"
          style={{
            fontSize: 'var(--text-hero)',
            color: `var(${meta.colorVar})`,
          }}
          aria-label={`판정 결과: ${meta.label}`}
        >
          {meta.label}
        </div>
        <div className="flex items-center gap-2 mt-1">
          <code
            className="px-1.5 py-0.5 rounded text-xs font-bold"
            style={{
              background: `var(${meta.colorVar})`,
              color: 'white',
              fontFamily: 'var(--font-mono)',
            }}
          >
            {meta.code}
          </code>
          <span className="text-sm" style={{ color: `var(${meta.colorVar})` }}>
            {meta.description}
          </span>
        </div>
      </div>

      {/* Confidence meter */}
      <div className="md:ml-auto flex flex-col items-end gap-1.5 min-w-[120px]">
        <div className="text-xs font-semibold uppercase tracking-widest" style={{ color: `var(${meta.colorVar})` }}>
          신뢰도
        </div>
        <div
          className="text-3xl font-black"
          style={{ color: `var(${meta.colorVar})` }}
          aria-label={`신뢰도 ${Math.round(confidence * 100)}%`}
        >
          {Math.round(confidence * 100)}
          <span className="text-lg font-semibold">%</span>
        </div>
        <div
          className="w-full h-2 rounded-full overflow-hidden"
          style={{ background: `var(${meta.borderVar})` }}
          role="progressbar"
          aria-valuenow={Math.round(confidence * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={`h-full rounded-full ${!reducedMotion ? 'transition-all duration-700' : ''}`}
            style={{
              width: `${Math.round(confidence * 100)}%`,
              background: `var(${meta.colorVar})`,
            }}
          />
        </div>
      </div>
    </div>
  )
}
