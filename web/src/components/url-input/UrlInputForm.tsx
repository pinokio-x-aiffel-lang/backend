import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { verifyRequestSchema } from '@/lib/api/schema'
import type { VerifyRequest } from '@/lib/api/schema'
import { Button } from '@/components/ui/Button'

interface UrlInputFormProps {
  onSubmit: (req: VerifyRequest) => void
  isLoading: boolean
}

export function UrlInputForm({ onSubmit, isLoading }: UrlInputFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<VerifyRequest>({ resolver: zodResolver(verifyRequestSchema) })

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="w-full max-w-2xl mx-auto" noValidate>
      <label
        htmlFor="article-url"
        className="block text-sm font-semibold mb-2"
        style={{ color: 'var(--color-text-secondary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}
      >
        기사 URL
      </label>

      <div className="flex gap-3">
        <div className="flex-1 relative">
          <input
            id="article-url"
            type="url"
            placeholder="https://news.example.com/article/12345"
            autoComplete="url"
            aria-describedby={errors.url ? 'url-error' : undefined}
            aria-invalid={!!errors.url}
            className="w-full rounded-lg px-4 py-3 text-base outline-none transition-all"
            style={{
              border: `1.5px solid ${errors.url ? 'var(--color-verdict-false)' : 'var(--color-border)'}`,
              background: 'var(--color-surface-elevated)',
              color: 'var(--color-text-primary)',
              fontFamily: 'var(--font-mono)',
            }}
            {...register('url', {
              onBlur: () => undefined,
            })}
          />
        </div>

        <Button type="submit" size="lg" loading={isLoading} disabled={isLoading}>
          {isLoading ? '검증 중' : '검증하기'}
        </Button>
      </div>

      {errors.url && (
        <p
          id="url-error"
          role="alert"
          className="mt-2 text-sm"
          style={{ color: 'var(--color-verdict-false)' }}
        >
          {errors.url.message}
        </p>
      )}

      <p className="mt-3 text-sm" style={{ color: 'var(--color-text-tertiary)' }}>
        tip: URL에 <code>article-2</code>, <code>article-3</code>, <code>article-4</code>,{' '}
        <code>article-5</code>를 포함하면 각 시나리오를 테스트할 수 있습니다
      </p>
    </form>
  )
}
