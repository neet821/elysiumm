import { forwardRef, useId } from 'react'

export const Input = forwardRef(function Input(
  {
    className,
    error,
    hint,
    id,
    label,
    required,
    'aria-describedby': ariaDescribedBy,
    ...inputProps
  },
  ref,
) {
  const generatedId = useId()
  const inputId = id || `input-${generatedId}`
  const hintId = hint ? `${inputId}-hint` : null
  const errorId = error ? `${inputId}-error` : null
  const describedBy = [ariaDescribedBy, hintId, errorId].filter(Boolean).join(' ') || undefined

  return (
    <div className={['ui-field', className].filter(Boolean).join(' ')}>
      {label && (
        <label className="ui-field__label" htmlFor={inputId}>
          {label}
          {required && <span className="ui-field__required" aria-hidden="true"> *</span>}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        className="ui-input"
        required={required}
        aria-describedby={describedBy}
        aria-invalid={error ? 'true' : undefined}
        {...inputProps}
      />
      {hint && <p className="ui-field__hint" id={hintId}>{hint}</p>}
      {error && <p className="ui-field__error" id={errorId}>{error}</p>}
    </div>
  )
})
