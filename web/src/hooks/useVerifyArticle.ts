import { useMutation } from '@tanstack/react-query'
import { verifyArticle } from '@/lib/api/verify'
import type { VerifyRequest, VerifyResponse } from '@/lib/api/schema'

export function useVerifyArticle() {
  return useMutation<VerifyResponse, Error, VerifyRequest>({
    mutationFn: verifyArticle,
  })
}
