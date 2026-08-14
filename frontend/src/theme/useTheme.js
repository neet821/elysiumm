import { useCallback, useRef, useState } from 'react'

function currentTheme() {
  if (typeof document === 'undefined') return 'light'
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

function setTransitionGeometry(event) {
  const root = document.documentElement
  const rect = event?.currentTarget?.getBoundingClientRect?.()
  const x = rect ? rect.left + rect.width / 2 : window.innerWidth / 2
  const y = rect ? rect.top + rect.height / 2 : window.innerHeight / 2
  const horizontalReach = Math.max(x, window.innerWidth - x)
  const verticalReach = Math.max(y, window.innerHeight - y)
  const radius = Math.hypot(horizontalReach, verticalReach)

  root.style.setProperty('--theme-origin-x', `${x}px`)
  root.style.setProperty('--theme-origin-y', `${y}px`)
  root.style.setProperty('--theme-radius', `${radius}px`)
}

export function useTheme() {
  const [theme, setTheme] = useState(currentTheme)
  const [isTransitioning, setIsTransitioning] = useState(false)
  const transitioningRef = useRef(false)

  const applyTheme = useCallback((nextTheme) => {
    const root = document.documentElement
    const nextIsDark = nextTheme === 'dark'
    root.classList.toggle('dark', nextIsDark)
    root.dataset.theme = nextTheme
    root.style.colorScheme = nextTheme
    window.localStorage.setItem('theme', nextTheme)
    setTheme(nextTheme)
  }, [])

  const finishTransition = useCallback(() => {
    transitioningRef.current = false
    document.documentElement.classList.remove('theme-transitioning')
    setIsTransitioning(false)
  }, [])

  const toggleTheme = useCallback((event) => {
    if (transitioningRef.current) return

    const nextTheme = theme === 'dark' ? 'light' : 'dark'
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const supportsViewTransition = typeof document.startViewTransition === 'function'

    setTransitionGeometry(event)
    if (reducedMotion || !supportsViewTransition) {
      applyTheme(nextTheme)
      return
    }

    transitioningRef.current = true
    setIsTransitioning(true)
    document.documentElement.classList.add('theme-transitioning')

    let transition
    try {
      transition = document.startViewTransition(() => applyTheme(nextTheme))
    } catch {
      applyTheme(nextTheme)
      finishTransition()
      return
    }

    Promise.resolve(transition?.finished)
      .catch(() => undefined)
      .finally(finishTransition)
  }, [applyTheme, finishTransition, theme])

  return {
    theme,
    isDark: theme === 'dark',
    isTransitioning,
    toggleTheme,
  }
}
