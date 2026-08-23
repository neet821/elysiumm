import { useEffect, useRef } from 'react'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

let scrollLockCount = 0
let previousBodyOverflow = ''

function lockBodyScroll() {
  if (scrollLockCount === 0) {
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
  scrollLockCount += 1
}

function unlockBodyScroll() {
  scrollLockCount = Math.max(0, scrollLockCount - 1)
  if (scrollLockCount === 0) {
    document.body.style.overflow = previousBodyOverflow
  }
}

function focusableElements(container) {
  return Array.from(container?.querySelectorAll(FOCUSABLE_SELECTOR) || [])
    .filter((element) => !element.hasAttribute('hidden'))
}

export function useDismissableLayer({ containerRef, initialFocusRef, onDismiss, open }) {
  const restoreFocusRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined

    restoreFocusRef.current = document.activeElement
    lockBodyScroll()

    const container = containerRef.current
    const initialTarget = initialFocusRef?.current || focusableElements(container)[0] || container
    initialTarget?.focus()

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        onDismiss()
        return
      }

      if (event.key !== 'Tab') return
      const focusable = focusableElements(containerRef.current)
      if (focusable.length === 0) {
        event.preventDefault()
        containerRef.current?.focus()
        return
      }

      const first = focusable[0]
      const last = focusable.at(-1)
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      unlockBodyScroll()
      const restoreTarget = restoreFocusRef.current
      if (restoreTarget instanceof HTMLElement && document.contains(restoreTarget)) {
        restoreTarget.focus()
      }
    }
  }, [containerRef, initialFocusRef, onDismiss, open])
}
