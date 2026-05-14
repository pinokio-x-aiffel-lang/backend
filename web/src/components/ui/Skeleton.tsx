interface SkeletonProps {
  className?: string
  width?: string
  height?: string
}

export function Skeleton({ className = '', width, height }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse rounded-lg ${className}`}
      style={{
        background: 'var(--color-border-subtle)',
        width: width ?? '100%',
        height: height ?? '1.25rem',
      }}
    />
  )
}
