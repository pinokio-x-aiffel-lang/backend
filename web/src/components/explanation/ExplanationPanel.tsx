import { Card } from '@/components/ui/Card'

interface ExplanationPanelProps {
  explanation: string
}

export function ExplanationPanel({ explanation }: ExplanationPanelProps) {
  return (
    <Card className="px-5 py-5">
      <h3
        className="text-xs font-bold uppercase tracking-widest mb-3"
        style={{ color: 'var(--color-text-tertiary)' }}
      >
        분석 설명
      </h3>
      <p
        className="leading-relaxed"
        style={{
          color: 'var(--color-text-primary)',
          fontSize: 'var(--text-base)',
          lineHeight: 1.8,
        }}
      >
        {explanation}
      </p>
    </Card>
  )
}
