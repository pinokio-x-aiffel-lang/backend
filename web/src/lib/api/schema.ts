import { z } from 'zod'

export const verdictSchema = z.enum(['T', 'F', 'M', 'N'])
// T=TRUE(진짜) F=FALSE(가짜) M=NEEDS_REVIEW(모호) N=NO_EVIDENCE(판단불가)

export const claimTypeSchema = z.enum([
  'absolute',
  'change_rate',
  'ratio',
  'distribution',
  'comparison',
  'metaphoric',
])

export const claimCardSchema = z.object({
  claim_id: z.string(),
  raw_text: z.string(),
  claim_type: claimTypeSchema,
  year: z.number().int().nullable(),
  compare_year: z.number().int().nullable(),
  item: z.string(),
  value: z.number().nullable(),
  unit: z.string(),
  population: z.string().nullable(),
  aggregation: z.string().nullable(),
  cited_source: z.string().nullable(),
})

export const kosisEvidenceSchema = z.object({
  table_id: z.string(),
  org_id: z.string(),
  table_name: z.string(),
  table_url: z.string().url(),
  period: z.string(),
  classification: z.record(z.string(), z.string()),
  official_value: z.number(),
  official_unit: z.string(),
  retrieved_at: z.string().datetime(),
})

export const numericComparisonSchema = z.object({
  article_value: z.number().nullable(),
  official_value: z.number(),
  unit: z.string(),
  abs_diff: z.number(),
  rel_diff_pct: z.number(),
  tolerance_pct: z.number(),
  within_tolerance: z.boolean(),
})

export const pipelineStepSchema = z.object({
  step: z.number().int(),
  name: z.string(),
  status: z.enum(['pending', 'running', 'done', 'skipped', 'error']),
  duration_ms: z.number().int().nullable(),
})

export const verifyResponseSchema = z.object({
  request_id: z.string(),
  article: z.object({
    url: z.string().url(),
    title: z.string().nullable(),
    published_at: z.string().nullable(),
  }),
  claim: claimCardSchema,
  all_claims: z.array(claimCardSchema),
  verdict: verdictSchema,
  confidence: z.number().min(0).max(1),
  evidence: kosisEvidenceSchema.nullable(),
  comparison: numericComparisonSchema.nullable(),
  explanation: z.string(),
  pipeline: z.array(pipelineStepSchema),
})

export const verifyRequestSchema = z.object({
  url: z.string().url('올바른 URL을 입력하세요'),
})

export type Verdict = z.infer<typeof verdictSchema>
export type ClaimType = z.infer<typeof claimTypeSchema>
export type ClaimCard = z.infer<typeof claimCardSchema>
export type KosisEvidence = z.infer<typeof kosisEvidenceSchema>
export type NumericComparison = z.infer<typeof numericComparisonSchema>
export type PipelineStep = z.infer<typeof pipelineStepSchema>
export type VerifyResponse = z.infer<typeof verifyResponseSchema>
export type VerifyRequest = z.infer<typeof verifyRequestSchema>
