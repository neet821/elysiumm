export function Tag({ children, className, tone = 'neutral', ...props }) {
  return (
    <span
      className={['ui-tag', `ui-tag--${tone}`, className].filter(Boolean).join(' ')}
      {...props}
    >
      {children}
    </span>
  )
}
