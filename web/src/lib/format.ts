export function formatNumber(n: number, decimals = 2): string {
  return n.toLocaleString('ko-KR', {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  })
}

export function formatPercent(n: number): string {
  return `${formatNumber(n, 1)}%`
}

export function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

export const CLAIM_TYPE_LABELS: Record<string, string> = {
  absolute: '절대값',
  change_rate: '증감률',
  ratio: '비율',
  distribution: '분포',
  comparison: '비교',
  metaphoric: '정성/추상',
}
