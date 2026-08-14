import { useCallback, useId, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useDismissableLayer } from './useDismissableLayer.js'

export function Drawer({
  children,
  className,
  description,
  initialFocusRef,
  onOpenChange,
  open,
  side = 'right',
  title,
}) {
  const drawerRef = useRef(null)
  const generatedId = useId()
  const titleId = `${generatedId}-title`
  const descriptionId = description ? `${generatedId}-description` : undefined
  const dismiss = useCallback(() => onOpenChange(false), [onOpenChange])

  useDismissableLayer({ containerRef: drawerRef, initialFocusRef, onDismiss: dismiss, open })

  if (!open || typeof document === 'undefined') return null

  return createPortal(
    <div
      className="ui-overlay__backdrop ui-drawer__backdrop"
      data-testid="drawer-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) dismiss()
      }}
    >
      <aside
        ref={drawerRef}
        className={['ui-drawer', className].filter(Boolean).join(' ')}
        data-side={side}
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
          <button className="ui-overlay__close" type="button" aria-label="关闭导航" onClick={dismiss}>
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <div className="ui-overlay__body">{children}</div>
      </aside>
    </div>,
    document.body,
  )
}
