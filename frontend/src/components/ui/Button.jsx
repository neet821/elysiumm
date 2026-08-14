import { forwardRef } from 'react'

function classNames(...values) {
  return values.filter(Boolean).join(' ')
}

export const Button = forwardRef(function Button(
  {
    children,
    className,
    disabled = false,
    isLoading = false,
    size = 'md',
    type = 'button',
    variant = 'primary',
    ...buttonProps
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={classNames(
        'ui-button',
        `ui-button--${variant}`,
        `ui-button--${size}`,
        className,
      )}
      disabled={disabled || isLoading}
      aria-busy={isLoading ? 'true' : undefined}
      {...buttonProps}
    >
      {isLoading && <span className="ui-button__spinner" aria-hidden="true" />}
      <span className="ui-button__label">{children}</span>
    </button>
  )
})

export const IconButton = forwardRef(function IconButton(
  { size = 'icon', variant = 'ghost', ...props },
  ref,
) {
  return <Button ref={ref} size={size} variant={variant} {...props} />
})
