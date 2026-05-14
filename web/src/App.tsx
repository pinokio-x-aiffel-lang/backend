import { useState } from 'react'
import { useVerifyArticle } from '@/hooks/useVerifyArticle'
import { usePipelineStepper } from '@/hooks/usePipelineStepper'
import { UrlInputForm } from '@/components/url-input/UrlInputForm'
import { PipelineProgress } from '@/components/pipeline/PipelineProgress'
import { ResultLayout } from '@/components/result/ResultLayout'
import type { VerifyResponse } from '@/lib/api/schema'

type AppState = 'idle' | 'loading' | 'result' | 'error'

/* ── 피노키오 코 SVG 아이콘 ── */
function NoseIcon({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 28 28"
      fill="none"
      aria-hidden="true"
    >
      <ellipse cx="14" cy="22" rx="5" ry="3" fill="currentColor" opacity="0.2" />
      <path
        d="M14 4 C14 4 10 10 8 16 C6.5 20 9 25 14 25 C19 25 21.5 20 20 16 C18 10 14 4 14 4Z"
        fill="currentColor"
        opacity="0.15"
      />
      <path
        d="M14 3 L14 20"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <path
        d="M14 20 Q10 24 7 22"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/* ── 판정 뱃지 샘플 (홈 쇼케이스용) ── */
const VERDICT_EXAMPLES = [
  {
    verdict: 'T',
    label: '진짜',
    code: 'TRUE',
    example: '청년실업률 5.9% — KOSIS와 일치',
    colorVar: '--color-verdict-true',
    bgVar: '--color-verdict-true-bg',
    borderVar: '--color-verdict-true-border',
  },
  {
    verdict: 'F',
    label: '가짜',
    code: 'FALSE',
    example: '합계출산율 0.95명 — 실제는 0.72명',
    colorVar: '--color-verdict-false',
    bgVar: '--color-verdict-false-bg',
    borderVar: '--color-verdict-false-border',
  },
  {
    verdict: 'M',
    label: '모호',
    code: 'NEEDS_REVIEW',
    example: '"물가가 크게 올랐다" — 수치 없음',
    colorVar: '--color-verdict-ambiguous',
    bgVar: '--color-verdict-ambiguous-bg',
    borderVar: '--color-verdict-ambiguous-border',
  },
  {
    verdict: 'N',
    label: '판단불가',
    code: 'NO_EVIDENCE',
    example: '소상공인 폐업률 — 통계 없음',
    colorVar: '--color-verdict-none',
    bgVar: '--color-verdict-none-bg',
    borderVar: '--color-verdict-none-border',
  },
] as const

/* ── 기능 소개 카드 데이터 ── */
const FEATURES = [
  {
    step: '01',
    title: '기사 URL 입력',
    desc: '검증하고 싶은 뉴스 기사 URL을 붙여넣기만 하면 됩니다.',
  },
  {
    step: '02',
    title: 'AI 9단계 분석',
    desc: 'NCP HyperCLOVA X가 주장을 탐지·구조화하고 KOSIS 통계를 검색합니다.',
  },
  {
    step: '03',
    title: '통계 대조 판정',
    desc: '통계청 공식 수치와 기사 수치를 비교해 4단계 판정 결과를 제공합니다.',
  },
] as const

export default function App() {
  const [appState, setAppState] = useState<AppState>('idle')
  const [result, setResult] = useState<VerifyResponse | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const mutation = useVerifyArticle()
  const currentStep = usePipelineStepper(appState === 'loading')

  function handleSubmit(req: { url: string }) {
    setAppState('loading')
    setResult(null)
    setErrorMsg(null)
    mutation.mutate(req, {
      onSuccess: (data) => { setResult(data); setAppState('result') },
      onError: (err) => { setErrorMsg(err.message); setAppState('error') },
    })
  }

  function handleReset() {
    setAppState('idle')
    setResult(null)
    setErrorMsg(null)
    mutation.reset()
  }

  return (
    <div className="min-h-dvh flex flex-col" style={{ background: 'var(--color-surface-base)' }}>

      {/* ── Header ── */}
      <header
        className="border-b sticky top-0 z-10"
        style={{ background: 'var(--color-surface-elevated)', borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-sm)' }}
      >
        <div className="flex items-center gap-2 px-6 py-3 mx-auto" style={{ maxWidth: 'var(--max-width)' }}>
          <span style={{ color: 'var(--color-accent)' }}>
            <NoseIcon size={22} />
          </span>
          <div className="font-black tracking-tight" style={{ fontSize: 'var(--text-xl)', letterSpacing: '-0.03em' }}>
            피노키오
            <span style={{ color: 'var(--color-accent)' }}>X</span>
          </div>
          <div
            className="ml-2 text-xs px-2 py-0.5 rounded-full font-semibold"
            style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}
          >
            BETA
          </div>
          {appState !== 'idle' && (
            <button
              onClick={handleReset}
              className="ml-auto text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
              style={{ color: 'var(--color-accent)', background: 'var(--color-accent-subtle)' }}
            >
              처음으로
            </button>
          )}
        </div>
      </header>

      {/* ── Main ── */}
      <main className="flex-1" style={{ maxWidth: 'var(--max-width)', margin: '0 auto', width: '100%' }}>

        {/* ══ IDLE: 메인 페이지 ══ */}
        {appState === 'idle' && (
          <>
            {/* ── Hero ── */}
            <section className="px-6 pt-16 pb-12 text-center relative overflow-hidden">
              {/* 배경 장식 */}
              <div
                aria-hidden="true"
                className="absolute inset-0 pointer-events-none"
                style={{
                  background: `radial-gradient(ellipse 60% 40% at 50% 0%, var(--color-accent-subtle) 0%, transparent 70%)`,
                }}
              />

              {/* 로고 */}
              <div className="relative flex flex-col items-center mb-6">
                <div
                  className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
                  style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}
                  aria-hidden="true"
                >
                  <NoseIcon size={36} />
                </div>
                <div
                  className="font-black tracking-tighter"
                  style={{ fontSize: 'clamp(2.5rem, 5vw, 4rem)', letterSpacing: '-0.04em', color: 'var(--color-text-primary)' }}
                >
                  피노키오
                  <span style={{ color: 'var(--color-accent)' }}>X</span>
                </div>
                <div
                  className="text-sm font-semibold mt-1 tracking-widest uppercase"
                  style={{ color: 'var(--color-text-tertiary)', letterSpacing: '0.15em' }}
                >
                  AI 뉴스 사실검증 시스템
                </div>
              </div>

              {/* 헤드라인 */}
              <h1
                className="font-bold mb-4 leading-tight relative"
                style={{ fontSize: 'clamp(1.5rem, 3vw, 2.25rem)', color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}
              >
                뉴스의 코가 자라고 있습니까?
              </h1>
              <p
                className="max-w-lg mx-auto mb-3 leading-relaxed relative"
                style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-lg)' }}
              >
                피노키오의 코처럼, 잘못된 수치는 숨길 수 없습니다.<br />
                기사 속 통계 주장을 <strong style={{ color: 'var(--color-text-primary)' }}>통계청 KOSIS 데이터</strong>와 대조해
                진위를 판정합니다.
              </p>

              {/* 신뢰 배지 */}
              <div className="flex flex-wrap items-center justify-center gap-2 mb-10 relative">
                {['통계청 KOSIS 연동', 'NCP HyperCLOVA X', '9단계 AI 파이프라인', '8-슬롯 구조화'].map((tag) => (
                  <span
                    key={tag}
                    className="text-xs px-3 py-1 rounded-full font-medium"
                    style={{ background: 'var(--color-surface-subtle)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}
                  >
                    {tag}
                  </span>
                ))}
              </div>

              {/* URL 입력 폼 */}
              <div className="relative max-w-2xl mx-auto">
                <UrlInputForm onSubmit={handleSubmit} isLoading={false} />
              </div>
            </section>

            {/* ── 작동 방식 (3단계) ── */}
            <section className="px-6 py-12" aria-labelledby="how-it-works">
              <h2
                id="how-it-works"
                className="text-center font-bold mb-8"
                style={{ fontSize: 'var(--text-2xl)', color: 'var(--color-text-primary)' }}
              >
                이렇게 작동합니다
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {FEATURES.map(({ step, title, desc }) => (
                  <div
                    key={step}
                    className="rounded-xl p-6 relative"
                    style={{ background: 'var(--color-surface-elevated)', border: '1px solid var(--color-border)', boxShadow: 'var(--shadow-sm)' }}
                  >
                    <div
                      className="font-black mb-3"
                      style={{ fontSize: 'var(--text-3xl)', color: 'var(--color-accent)', opacity: 0.25, fontFamily: 'var(--font-mono)', lineHeight: 1 }}
                      aria-hidden="true"
                    >
                      {step}
                    </div>
                    <h3 className="font-bold mb-2" style={{ fontSize: 'var(--text-lg)', color: 'var(--color-text-primary)' }}>
                      {title}
                    </h3>
                    <p className="text-sm leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                      {desc}
                    </p>
                  </div>
                ))}
              </div>
            </section>

            {/* ── 판정 결과 예시 ── */}
            <section className="px-6 py-12" style={{ background: 'var(--color-surface-subtle)' }} aria-labelledby="verdict-examples">
              <h2
                id="verdict-examples"
                className="text-center font-bold mb-2"
                style={{ fontSize: 'var(--text-2xl)', color: 'var(--color-text-primary)' }}
              >
                4가지 판정 결과
              </h2>
              <p
                className="text-center text-sm mb-8"
                style={{ color: 'var(--color-text-tertiary)' }}
              >
                단순한 참/거짓이 아닌, 맥락을 반영한 4단계 판정
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 max-w-4xl mx-auto">
                {VERDICT_EXAMPLES.map(({ label, code, example, colorVar, bgVar, borderVar }) => (
                  <div
                    key={code}
                    className="rounded-xl p-4"
                    style={{
                      background: `var(${bgVar})`,
                      border: `1.5px solid var(${borderVar})`,
                    }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span
                        className="font-black text-xl"
                        style={{ color: `var(${colorVar})` }}
                      >
                        {label}
                      </span>
                      <code
                        className="text-xs px-1.5 py-0.5 rounded font-bold"
                        style={{ background: `var(${colorVar})`, color: 'white', fontFamily: 'var(--font-mono)' }}
                      >
                        {code.split('_')[0]}
                      </code>
                    </div>
                    <p className="text-xs leading-snug" style={{ color: `var(${colorVar})`, opacity: 0.8 }}>
                      {example}
                    </p>
                  </div>
                ))}
              </div>
            </section>

            {/* ── 하단 CTA ── */}
            <section className="px-6 py-16 text-center" aria-labelledby="bottom-cta">
              <div
                className="max-w-xl mx-auto rounded-2xl p-8"
                style={{ background: 'var(--color-surface-elevated)', border: '2px solid var(--color-accent-subtle)', boxShadow: 'var(--shadow-md)' }}
              >
                <div
                  className="text-3xl mb-3 font-black"
                  style={{ color: 'var(--color-accent)' }}
                  aria-hidden="true"
                >
                  🔍
                </div>
                <h2
                  id="bottom-cta"
                  className="font-bold mb-2"
                  style={{ fontSize: 'var(--text-2xl)', color: 'var(--color-text-primary)' }}
                >
                  지금 바로 확인해보세요
                </h2>
                <p className="text-sm mb-6" style={{ color: 'var(--color-text-secondary)' }}>
                  의심스러운 뉴스 기사 URL을 붙여넣고 검증을 시작하세요
                </p>
                <UrlInputForm onSubmit={handleSubmit} isLoading={false} />
              </div>
            </section>
          </>
        )}

        {/* ══ LOADING ══ */}
        {appState === 'loading' && (
          <section className="max-w-2xl mx-auto px-6 py-16" aria-live="polite" aria-label="검증 진행 중">
            <div className="text-center mb-8">
              <div style={{ color: 'var(--color-accent)' }} className="flex justify-center mb-4">
                <NoseIcon size={40} />
              </div>
              <h2 className="font-bold mb-2" style={{ fontSize: 'var(--text-2xl)', color: 'var(--color-text-primary)' }}>
                코가 자라는지 확인 중...
              </h2>
              <p className="text-sm" style={{ color: 'var(--color-text-tertiary)' }}>
                KOSIS 통계 조회 및 수치 비교에 10~20초가 소요됩니다
              </p>
            </div>
            <PipelineProgress currentStep={currentStep} />
          </section>
        )}

        {/* ══ RESULT ══ */}
        {appState === 'result' && result && (
          <div className="px-4 py-10">
            <ResultLayout result={result} onReset={handleReset} />
          </div>
        )}

        {/* ══ ERROR ══ */}
        {appState === 'error' && (
          <section className="max-w-lg mx-auto px-6 py-16 text-center">
            <div
              className="rounded-2xl p-8 mb-6"
              style={{ background: 'var(--color-verdict-false-bg)', border: '2px solid var(--color-verdict-false-border)' }}
            >
              <div className="text-4xl font-black mb-2" style={{ color: 'var(--color-verdict-false)' }} aria-hidden="true">!</div>
              <p className="font-semibold mb-1" style={{ color: 'var(--color-verdict-false)' }}>검증 실패</p>
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>{errorMsg}</p>
            </div>
            <UrlInputForm onSubmit={handleSubmit} isLoading={false} />
          </section>
        )}
      </main>

      {/* ── Footer ── */}
      <footer
        className="border-t py-5 text-center"
        style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-tertiary)' }}
      >
        <div className="flex items-center justify-center gap-1.5 mb-1">
          <span style={{ color: 'var(--color-accent)' }}><NoseIcon size={14} /></span>
          <span className="font-bold text-sm" style={{ color: 'var(--color-text-primary)' }}>
            피노키오<span style={{ color: 'var(--color-accent)' }}>X</span>
          </span>
          <span className="text-xs">— 아이펠 엔지니어 1기 기업프로젝트</span>
        </div>
        <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
          POC 데모 ·{' '}
          <code style={{ fontFamily: 'var(--font-mono)' }}>VITE_USE_MOCK={import.meta.env.VITE_USE_MOCK}</code>
        </p>
      </footer>
    </div>
  )
}
