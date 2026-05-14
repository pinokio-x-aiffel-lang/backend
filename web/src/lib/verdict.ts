import type { Verdict } from './api/schema'

interface VerdictMeta {
  label: string
  code: string
  description: string
  colorVar: string
  bgVar: string
  borderVar: string
}

export const VERDICT_META: Record<Verdict, VerdictMeta> = {
  T: {
    label: '진짜',
    code: 'TRUE',
    description: '기사의 수치가 공식 통계와 일치합니다',
    colorVar: '--color-verdict-true',
    bgVar: '--color-verdict-true-bg',
    borderVar: '--color-verdict-true-border',
  },
  F: {
    label: '가짜',
    code: 'FALSE',
    description: '기사의 수치가 공식 통계와 불일치합니다',
    colorVar: '--color-verdict-false',
    bgVar: '--color-verdict-false-bg',
    borderVar: '--color-verdict-false-border',
  },
  M: {
    label: '모호',
    code: 'NEEDS_REVIEW',
    description: '정량적 비교가 어렵거나 판정이 불확실합니다',
    colorVar: '--color-verdict-ambiguous',
    bgVar: '--color-verdict-ambiguous-bg',
    borderVar: '--color-verdict-ambiguous-border',
  },
  N: {
    label: '판단불가',
    code: 'NO_EVIDENCE',
    description: '대응하는 KOSIS 통계를 찾을 수 없습니다',
    colorVar: '--color-verdict-none',
    bgVar: '--color-verdict-none-bg',
    borderVar: '--color-verdict-none-border',
  },
}

export function getVerdictMeta(verdict: Verdict): VerdictMeta {
  return VERDICT_META[verdict]
}
