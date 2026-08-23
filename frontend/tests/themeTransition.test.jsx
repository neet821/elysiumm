import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useTheme } from '../src/theme/useTheme.js'

function setMatchMedia(reducedMotion) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockImplementation((query) => ({
      matches: query === '(prefers-reduced-motion: reduce)' ? reducedMotion : false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  })
}

function themeEvent() {
  const button = document.createElement('button')
  button.getBoundingClientRect = vi.fn(() => ({
    bottom: 70,
    height: 20,
    left: 100,
    right: 150,
    top: 50,
    width: 50,
    x: 100,
    y: 50,
  }))
  return { currentTarget: button }
}

beforeEach(() => {
  document.documentElement.className = ''
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.removeAttribute('style')
  window.localStorage.clear()
  setMatchMedia(false)
  delete document.startViewTransition
})

describe('useTheme', () => {
  it('uses the trigger center and applies the new theme inside the view transition callback', async () => {
    let applyTransition
    let finishTransition
    document.startViewTransition = vi.fn((callback) => {
      applyTransition = callback
      return { finished: new Promise((resolve) => { finishTransition = resolve }) }
    })
    const { result } = renderHook(() => useTheme())

    act(() => result.current.toggleTheme(themeEvent()))

    expect(document.documentElement.style.getPropertyValue('--theme-origin-x')).toBe('125px')
    expect(document.documentElement.style.getPropertyValue('--theme-origin-y')).toBe('60px')
    expect(document.documentElement.style.getPropertyValue('--theme-radius')).toMatch(/^\d+(\.\d+)?px$/)
    expect(document.documentElement).not.toHaveClass('dark')

    act(() => applyTransition())
    expect(document.documentElement).toHaveClass('dark')
    expect(window.localStorage.getItem('theme')).toBe('dark')
    expect(result.current.isTransitioning).toBe(true)

    await act(async () => {
      finishTransition()
      await Promise.resolve()
    })
    expect(result.current.isTransitioning).toBe(false)
  })

  it('switches immediately when View Transitions are unavailable', () => {
    const { result } = renderHook(() => useTheme())

    act(() => result.current.toggleTheme(themeEvent()))

    expect(result.current.theme).toBe('dark')
    expect(document.documentElement).toHaveClass('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('skips animated transitions for reduced motion', () => {
    setMatchMedia(true)
    document.startViewTransition = vi.fn()
    const { result } = renderHook(() => useTheme())

    act(() => result.current.toggleTheme(themeEvent()))

    expect(document.startViewTransition).not.toHaveBeenCalled()
    expect(result.current.theme).toBe('dark')
  })

  it('ignores a second toggle while a transition is active', async () => {
    let applyTransition
    let finishTransition
    document.startViewTransition = vi.fn((callback) => {
      applyTransition = callback
      return { finished: new Promise((resolve) => { finishTransition = resolve }) }
    })
    const { result } = renderHook(() => useTheme())

    act(() => {
      result.current.toggleTheme(themeEvent())
      result.current.toggleTheme(themeEvent())
    })

    expect(document.startViewTransition).toHaveBeenCalledTimes(1)
    act(() => applyTransition())
    await act(async () => {
      finishTransition()
      await Promise.resolve()
    })
    expect(result.current.theme).toBe('dark')
  })
})
