import type { PipelineStep, VerifyResponse } from './schema'

const PIPELINE_DONE: PipelineStep[] = [
  { step: 1, name: '기사 내용 추출', status: 'done', duration_ms: 420 },
  { step: 2, name: '주장 탐지', status: 'done', duration_ms: 1850 },
  { step: 3, name: '주장 분류', status: 'done', duration_ms: 980 },
  { step: 4, name: '주장 구조화 (8-슬롯)', status: 'done', duration_ms: 1340 },
  { step: 5, name: 'KOSIS 카탈로그 필터링', status: 'done', duration_ms: 210 },
  { step: 6, name: '임베딩 검색 (Top-50)', status: 'done', duration_ms: 760 },
  { step: 7, name: '재순위화 (Top-5)', status: 'done', duration_ms: 890 },
  { step: 8, name: 'RAG 추론 (Top-1)', status: 'done', duration_ms: 2100 },
  { step: 9, name: 'KOSIS API + 수치 비교', status: 'done', duration_ms: 1450 },
]

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

const SCENARIOS: VerifyResponse[] = [
  {
    request_id: 'mock-req-001',
    article: { url: '', title: '2023년 청년실업률 5.9%...전년比 소폭 개선', published_at: '2024-01-15T09:00:00Z' },
    claim: {
      claim_id: 'claim-001',
      raw_text: '2023년 청년(15~29세) 실업률은 5.9%였다.',
      claim_type: 'absolute',
      year: 2023, compare_year: null,
      item: '청년 실업률', value: 5.9, unit: '%',
      population: '15~29세', aggregation: '연간 평균', cited_source: '통계청 고용동향',
    },
    all_claims: [],
    verdict: 'T',
    confidence: 0.92,
    evidence: {
      table_id: 'DT_1DA7001S', org_id: '101',
      table_name: '고용동향 - 실업률 (연령별)',
      table_url: 'https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1DA7001S',
      period: '2023', classification: { C1: '청년층 (15~29세)' },
      official_value: 5.9, official_unit: '%', retrieved_at: '2024-01-15T09:05:00Z',
    },
    comparison: { article_value: 5.9, official_value: 5.9, unit: '%', abs_diff: 0, rel_diff_pct: 0, tolerance_pct: 0.1, within_tolerance: true },
    explanation: '이 기사는 2023년 청년(15~29세) 실업률을 5.9%로 인용하였습니다. 통계청 고용동향 (표: DT_1DA7001S)의 2023년 청년층 연간 평균 실업률은 5.9%로, 기사의 수치와 정확히 일치합니다.',
    pipeline: PIPELINE_DONE,
  },
  {
    request_id: 'mock-req-002',
    article: { url: '', title: '2023년 합계출산율 0.95명...인구절벽 현실화', published_at: '2024-02-08T10:30:00Z' },
    claim: {
      claim_id: 'claim-002',
      raw_text: '2023년 합계출산율은 0.95명이었다.',
      claim_type: 'absolute',
      year: 2023, compare_year: null,
      item: '합계출산율', value: 0.95, unit: '명',
      population: '전국', aggregation: '연간', cited_source: '통계청',
    },
    all_claims: [],
    verdict: 'F',
    confidence: 0.88,
    evidence: {
      table_id: 'DT_1B8000F', org_id: '101',
      table_name: '출생통계 - 합계출산율',
      table_url: 'https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B8000F',
      period: '2023', classification: { C1: '전국' },
      official_value: 0.72, official_unit: '명', retrieved_at: '2024-02-08T10:35:00Z',
    },
    comparison: { article_value: 0.95, official_value: 0.72, unit: '명', abs_diff: 0.23, rel_diff_pct: 31.9, tolerance_pct: 0.05, within_tolerance: false },
    explanation: '이 기사는 2023년 합계출산율을 0.95명으로 인용하였습니다. 그러나 통계청 출생통계 (표: DT_1B8000F)의 2023년 합계출산율은 0.72명입니다. 기사가 인용한 수치는 실제 통계보다 약 32% 높게 기재되었습니다.',
    pipeline: PIPELINE_DONE,
  },
  {
    request_id: 'mock-req-003',
    article: { url: '', title: '최근 물가 급등...서민 생활고 심화', published_at: '2024-03-12T08:00:00Z' },
    claim: {
      claim_id: 'claim-003',
      raw_text: '최근 물가가 크게 올랐다.',
      claim_type: 'metaphoric',
      year: 2024, compare_year: 2023,
      item: '소비자물가지수', value: null, unit: '%',
      population: '전국', aggregation: '월간', cited_source: null,
    },
    all_claims: [],
    verdict: 'M',
    confidence: 0.35,
    evidence: null,
    comparison: null,
    explanation: '이 기사의 주장 "최근 물가가 크게 올랐다"는 구체적인 수치를 포함하지 않아 정량적 비교가 어렵습니다. "크게"의 기준이 불명확하여 일치/불일치를 판정하기 어렵습니다.',
    pipeline: PIPELINE_DONE,
  },
  {
    request_id: 'mock-req-004',
    article: { url: '', title: '소상공인 폐업 역대 최고...경기침체 직격탄', published_at: '2024-04-01T11:00:00Z' },
    claim: {
      claim_id: 'claim-004',
      raw_text: '2023년 소상공인 폐업률이 역대 최고를 기록했다.',
      claim_type: 'absolute',
      year: 2023, compare_year: null,
      item: '소상공인 폐업률', value: null, unit: '%',
      population: '소상공인', aggregation: '연간', cited_source: null,
    },
    all_claims: [],
    verdict: 'N',
    confidence: 0,
    evidence: null,
    comparison: null,
    explanation: '이 기사의 주장에 대응하는 KOSIS 통계표를 찾을 수 없었습니다. "소상공인 폐업률"은 현재 KOSIS 카탈로그에 등록되어 있지 않아 사실검증이 불가능합니다.',
    pipeline: [
      ...PIPELINE_DONE.slice(0, 5),
      { step: 6, name: '임베딩 검색 (Top-50)', status: 'error', duration_ms: 890 },
      { step: 7, name: '재순위화 (Top-5)', status: 'skipped', duration_ms: null },
      { step: 8, name: 'RAG 추론 (Top-1)', status: 'skipped', duration_ms: null },
      { step: 9, name: 'KOSIS API + 수치 비교', status: 'skipped', duration_ms: null },
    ],
  },
  {
    request_id: 'mock-req-005',
    article: { url: '', title: '내년 경제성장률 2.5% 전망...수출 회복 기대', published_at: '2024-05-20T09:30:00Z' },
    claim: {
      claim_id: 'claim-005',
      raw_text: '내년 경제성장률은 2.5%로 전망된다.',
      claim_type: 'change_rate',
      year: 2025, compare_year: 2024,
      item: '경제성장률', value: 2.5, unit: '%',
      population: '한국', aggregation: '연간', cited_source: 'KDI',
    },
    all_claims: [],
    verdict: 'M',
    confidence: 0.2,
    evidence: null,
    comparison: null,
    explanation: '이 기사의 주장은 미래 전망치(예측)로, 공식 실측 데이터와 비교할 수 없습니다. 본 시스템은 실측 통계와만 비교합니다.',
    pipeline: [
      ...PIPELINE_DONE.slice(0, 5),
      { step: 6, name: '임베딩 검색 (Top-50)', status: 'skipped', duration_ms: null },
      { step: 7, name: '재순위화 (Top-5)', status: 'skipped', duration_ms: null },
      { step: 8, name: 'RAG 추론 (Top-1)', status: 'skipped', duration_ms: null },
      { step: 9, name: 'KOSIS API + 수치 비교', status: 'skipped', duration_ms: null },
    ],
  },
]

export async function getMockResponse(url: string): Promise<VerifyResponse> {
  const lower = url.toLowerCase()
  let idx = 0

  if (lower.includes('false') || lower.includes('article-2')) idx = 1
  else if (lower.includes('ambiguous') || lower.includes('article-3')) idx = 2
  else if (lower.includes('none') || lower.includes('article-4')) idx = 3
  else if (lower.includes('forecast') || lower.includes('article-5')) idx = 4
  else {
    const hash = [...url].reduce((acc, c) => acc + c.charCodeAt(0), 0)
    idx = hash % SCENARIOS.length
  }

  await delay(12_000 + Math.random() * 4_000)

  const s = SCENARIOS[idx]
  return { ...s, article: { ...s.article, url } }
}
