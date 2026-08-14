import { useCallback, useEffect, useMemo, useState } from 'react'
import { ToastContext } from './toastContext.js'

function ToastItem({ onDismiss, toast }) {
  useEffect(() => {
    if (toast.duration === 0) return undefined
    const timer = window.setTimeout(() => onDismiss(toast.id), toast.duration)
    return () => window.clearTimeout(timer)
  }, [onDismiss, toast.duration, toast.id])

  return (
    <div className="ui-toast" data-tone={toast.tone} role="status">
      <div className="ui-toast__content">
        <strong className="ui-toast__title">{toast.title}</strong>
        {toast.description && <p className="ui-toast__description">{toast.description}</p>}
      </div>
      <button
        className="ui-toast__close"
        type="button"
        aria-label={`Dismiss ${toast.title}`}
        onClick={() => onDismiss(toast.id)}
      >
        <span aria-hidden="true">×</span>
      </button>
    </div>
  )
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const remove = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const push = useCallback((toast) => {
    const id = globalThis.crypto?.randomUUID?.() || `toast-${Date.now()}-${Math.random()}`
    setToasts((current) => [
      ...current,
      { duration: 4000, tone: 'neutral', ...toast, id },
    ])
    return id
  }, [])

  const value = useMemo(() => ({ push, remove }), [push, remove])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="ui-toast-viewport" aria-live="polite" aria-label="通知">
        {toasts.map((toast) => <ToastItem key={toast.id} toast={toast} onDismiss={remove} />)}
      </div>
    </ToastContext.Provider>
  )
}
