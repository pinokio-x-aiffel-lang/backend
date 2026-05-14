import type { ButtonHTMLAttributes, ReactNode } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'outline' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  children: ReactNode
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  children,
  disabled,
  className = '',
  ...props
}: ButtonProps) {
  const base =
    'inline-flex items-center justify-center font-semibold rounded-lg transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed'

  const sizes = {
    sm: 'px-3 py-1.5 text-sm gap-1.5',
    md: 'px-5 py-2.5 text-base gap-2',
    lg: 'px-7 py-3.5 text-lg gap-2',
  }

  const variants = {
    primary: [
      'text-white',
      'focus-visible:ring-[var(--color-accent)]',
    ].join(' '),
    outline: [
      'border border-[var(--color-border)] text-[var(--color-text-primary)]',
      'hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]',
      'focus-visible:ring-[var(--color-accent)]',
    ].join(' '),
    ghost: [
      'text-[var(--color-text-secondary)]',
      'hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-subtle)]',
      'focus-visible:ring-[var(--color-accent)]',
    ].join(' '),
  }

  return (
    <button
      {...props}
      disabled={disabled ?? loading}
      className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}
      style={
        variant === 'primary'
          ? {
              background: 'var(--color-accent)',
              ...(props.style ?? {}),
            }
          : props.style
      }
    >
      {loading ? (
        <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      ) : null}
      {children}
    </button>
  )
}
