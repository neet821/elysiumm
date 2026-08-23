export function Skeleton({ className, label = '正在载入', ...props }) {
  return (
    <span
      className={['ui-skeleton', className].filter(Boolean).join(' ')}
      role="status"
      aria-label={label}
      {...props}
    />
  )
}
