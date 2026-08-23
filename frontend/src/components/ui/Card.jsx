import { forwardRef } from 'react'

export const Card = forwardRef(function Card(
  { as: Component = 'div', className, interactive = false, muted = false, ...props },
  ref,
) {
  return (
    <Component
      ref={ref}
      className={[
        'ui-card',
        interactive && 'ui-card--interactive',
        muted && 'ui-card--muted',
        className,
      ].filter(Boolean).join(' ')}
      {...props}
    />
  )
})
