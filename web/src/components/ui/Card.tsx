import type { HTMLAttributes, ReactNode } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  elevated?: boolean
}

export function Card({ children, elevated = false, className = '', style, ...props }: CardProps) {
  return (
    <div
      {...props}
      className={`rounded-xl border ${className}`}
      style={{
        background: elevated
          ? 'var(--color-surface-elevated)'
          : 'var(--color-surface-elevated)',
        borderColor: 'var(--color-border)',
        boxShadow: elevated ? 'var(--shadow-md)' : 'var(--shadow-sm)',
        ...style,
      }}
    >
      {children}
    </div>
  )
}
