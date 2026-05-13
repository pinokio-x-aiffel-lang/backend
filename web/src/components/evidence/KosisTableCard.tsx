import { ExternalLink } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import type { KosisEvidence } from '@/lib/api/schema'
import { formatDate, formatNumber } from '@/lib/format'

interface KosisTableCardProps {
  evidence: KosisEvidence
}

export function KosisTableCard({ evidence }: KosisTableCardProps) {
  return (
    <Card className="overflow-hidden">
      <div
        className="flex items-stretch"
        style={{ borderLeft: '4px solid var(--color-accent)' }}
      >
        <div className="flex-1 px-5 py-5">
          <div
            className="text-xs font-bold uppercase tracking-widest mb-2"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            KOSIS 통계 출처
          </div>

          <h3
            className="font-bold text-base leading-snug mb-1"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {evidence.table_name}
          </h3>

          <div className="flex items-center gap-2 mb-4">
            <code
              className="text-xs px-1.5 py-0.5 rounded"
              style={{
                background: 'var(--color-surface-subtle)',
                color: 'var(--color-text-secondary)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {evidence.table_id}
            </code>
            <a
              href={evidence.table_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs font-medium transition-colors"
              style={{ color: 'var(--color-accent)' }}
              aria-label="KOSIS에서 통계표 열기 (새 창)"
            >
              KOSIS에서 보기
              <ExternalLink size={12} aria-hidden="true" />
            </a>
          </div>

          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm mb-4">
            <div>
              <span className="text-xs font-semibold" style={{ color: 'var(--color-text-tertiary)' }}>
                기준연도
              </span>
              <p style={{ color: 'var(--color-text-primary)' }}>{evidence.period}</p>
            </div>
            {(Object.entries(evidence.classification) as [string, string][]).map(([key, val]) => (
              <div key={key}>
                <span className="text-xs font-semibold" style={{ color: 'var(--color-text-tertiary)' }}>
                  분류
                </span>
                <p style={{ color: 'var(--color-text-primary)' }}>{val}</p>
              </div>
            ))}
          </div>

          <div
            className="rounded-lg px-4 py-3 flex items-baseline gap-1.5"
            style={{ background: 'var(--color-accent-subtle)' }}
          >
            <span className="text-xs font-semibold" style={{ color: 'var(--color-accent)' }}>
              공식 수치
            </span>
            <span
              className="text-2xl font-black"
              style={{ color: 'var(--color-accent)', fontFamily: 'var(--font-mono)' }}
            >
              {formatNumber(evidence.official_value)}
            </span>
            <span className="text-sm font-semibold" style={{ color: 'var(--color-accent)' }}>
              {evidence.official_unit}
            </span>
          </div>

          <p
            className="mt-3 text-xs"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            조회일: {formatDate(evidence.retrieved_at)}
          </p>
        </div>
      </div>
    </Card>
  )
}
