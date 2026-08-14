import { useCallback, useId, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useDismissableLayer } from './useDismissableLayer.js'

export function Dialog({
  children,
  className,
  description,
  initialFocusRef,
  onOpenChange,
  open,
  title,
}) {
  const dialogRef = useRef(null)
  const generatedId = useId()
  const titleId = `${generatedId}-title`
  const descriptionId = description ? `${generatedId}-description` : undefined
  const dismiss = useCallback(() => onOpenChange(false), [onOpenChange])

  useDismissableLayer({ containerRef: dialogRef, initialFocusRef, onDismiss: dismiss, open })

  if (!open || typeof document === 'undefined') return null

  return createPortal(
    <div
      className="ui-overlay__backdrop"
      data-testid="dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) dismiss()
      }}
    >
      <section
        ref={dialogRef}
        className={['ui-dialog', className].filter(Boolean).join(' ')}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
      >
        <header className="ui-overlay__header">
          <div>
            <h2 className="ui-overlay__title" id={titleId}>{title}</h2>
            {description && <p className="ui-overlay__description" id={descriptionId}>{description}</p>}
          </div>
          <button className="ui-overlay__close" type="button" aria-label="关闭对话框" onClick={dismiss}>
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <div className="ui-overlay__body">{children}</div>
      </section>
    </div>,
    document.body,
  )
}
