import { apiFetch } from './client'
import { verifyResponseSchema } from './schema'
import type { VerifyRequest, VerifyResponse } from './schema'
import { getMockResponse } from './mock'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export async function verifyArticle(req: VerifyRequest): Promise<VerifyResponse> {
  if (USE_MOCK) {
    return getMockResponse(req.url)
  }

  const raw = await apiFetch<unknown>('/verify', {
    method: 'POST',
    body: JSON.stringify(req),
  })

  const parsed = verifyResponseSchema.safeParse(raw)
  if (!parsed.success) {
    throw new Error('응답 형식이 예상과 다릅니다. (백엔드 스키마 확인 필요)')
  }

  return parsed.data
}
