import { Card } from '@/components/ui/Card'
import type { NumericComparison as NumericComparisonType } from '@/lib/api/schema'
import { formatNumber } from '@/lib/format'

interface NumericComparisonProps {
  comparison: NumericComparisonType
}

export function NumericComparison({ comparison }: NumericComparisonProps) {
  const { within_tolerance, article_value, official_value, unit, abs_diff, rel_diff_pct, tolerance_pct } =
    comparison

  const matchColor = within_tolerance ? 'var(--color-verdict-true)' : 'var(--color-verdict-false)'
  const matchBg = within_tolerance ? 'var(--color-verdict-true-bg)' : 'var(--color-verdict-false-bg)'
  const matchBorder = within_tolerance ? 'var(--color-verdict-true-border)' : 'var(--color-verdict-false-border)'

  return (
    <Card className="overflow-hidden">
      <div className="px-5 pt-5 pb-2">
        <h3
          className="text-xs font-bold uppercase tracking-widest mb-4"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          수치 비교
        </h3>

        <div className="grid grid-cols-2 gap-4 mb-5">
          <div
            className="rounded-xl p-4 text-center"
            style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)' }}
          >
            <div
              className="text-xs font-semibold uppercase tracking-wider mb-1"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              기사 수치
            </div>
            <div
              className="text-2xl font-black"
              style={{ color: 'var(--color-text-primary)', fontFamily: 'var(--font-mono)' }}
            >
              {article_value !== null ? `${formatNumber(article_value)} ${unit}` : '—'}
            </div>
          </div>

          <div
            className="rounded-xl p-4 text-center"
            style={{ background: matchBg, border: `1px solid ${matchBorder}` }}
          >
            <div
              className="text-xs font-semibold uppercase tracking-wider mb-1"
              style={{ color: matchColor }}
            >
              KOSIS 공식
            </div>
            <div
              className="text-2xl font-black"
              style={{ color: matchColor, fontFamily: 'var(--font-mono)' }}
            >
              {formatNumber(official_value)} {unit}
            </div>
          </div>
        </div>

        <div
          className="rounded-lg px-4 py-3 flex items-center justify-between"
          style={{ background: matchBg, border: `1px solid ${matchBorder}` }}
        >
          <div className="flex items-center gap-2">
            <span
              className="text-lg font-black"
              style={{ color: matchColor }}
              aria-label={within_tolerance ? '허용 오차 이내' : '오차 초과'}
            >
              {within_tolerance ? '✓' : '✕'}
            </span>
            <span className="font-semibold text-sm" style={{ color: matchColor }}>
              {within_tolerance ? '허용 오차 이내' : '수치 불일치'}
            </span>
          </div>
          <div className="text-right text-sm" style={{ color: matchColor }}>
            <div>
              차이:{' '}
              <strong style={{ fontFamily: 'var(--font-mono)' }}>
                {formatNumber(abs_diff)} {unit}
              </strong>
            </div>
            <div>
              오차율:{' '}
              <strong style={{ fontFamily: 'var(--font-mono)' }}>
                {formatNumber(rel_diff_pct, 1)}%
              </strong>{' '}
              <span style={{ color: 'var(--color-text-tertiary)', fontSize: 'var(--text-xs)' }}>
                (허용 ±{formatNumber(tolerance_pct * 100, 0)}%)
              </span>
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}
