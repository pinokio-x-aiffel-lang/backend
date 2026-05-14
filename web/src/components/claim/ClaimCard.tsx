import { Card } from '@/components/ui/Card'
import type { ClaimCard as ClaimCardType } from '@/lib/api/schema'
import { CLAIM_TYPE_LABELS, formatNumber } from '@/lib/format'

interface ClaimCardProps {
  claim: ClaimCardType
}

export function ClaimCard({ claim }: ClaimCardProps) {
  const slots: Array<{ label: string; value: string | null }> = [
    { label: '년도', value: claim.year !== null ? String(claim.year) : null },
    { label: '비교년도', value: claim.compare_year !== null ? String(claim.compare_year) : null },
    { label: '항목', value: claim.item },
    { label: '수치', value: claim.value !== null ? `${formatNumber(claim.value)} ${claim.unit}` : null },
    { label: '모집단', value: claim.population },
    { label: '집계방식', value: claim.aggregation },
    { label: '인용출처', value: claim.cited_source },
    { label: '주장유형', value: CLAIM_TYPE_LABELS[claim.claim_type] ?? claim.claim_type },
  ]

  return (
    <Card className="overflow-hidden">
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-center justify-between mb-3">
          <h3
            className="text-xs font-bold uppercase tracking-widest"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            추출된 주장
          </h3>
          <span
            className="text-xs px-2 py-0.5 rounded font-mono font-semibold"
            style={{
              background: 'var(--color-accent-subtle)',
              color: 'var(--color-accent)',
            }}
          >
            {CLAIM_TYPE_LABELS[claim.claim_type] ?? claim.claim_type}
          </span>
        </div>

        <blockquote
          className="text-base leading-relaxed border-l-4 pl-4 py-1"
          style={{
            borderColor: 'var(--color-accent)',
            background: 'var(--color-surface-subtle)',
            borderRadius: '0 var(--radius-md) var(--radius-md) 0',
            color: 'var(--color-text-primary)',
          }}
        >
          &ldquo;{claim.raw_text}&rdquo;
        </blockquote>
      </div>

      <div
        className="border-t"
        style={{ borderColor: 'var(--color-border-subtle)' }}
      >
        <table className="w-full text-sm">
          <tbody>
            {slots.map(({ label, value }) => (
              <tr
                key={label}
                className="border-b last:border-b-0"
                style={{ borderColor: 'var(--color-border-subtle)' }}
              >
                <td
                  className="px-5 py-2.5 font-semibold whitespace-nowrap w-28"
                  style={{ color: 'var(--color-text-tertiary)', fontSize: 'var(--text-xs)' }}
                >
                  {label}
                </td>
                <td
                  className="px-5 py-2.5"
                  style={{
                    color: value ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
                    fontFamily: value ? 'var(--font-mono)' : undefined,
                    fontSize: 'var(--text-sm)',
                  }}
                >
                  {value ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
