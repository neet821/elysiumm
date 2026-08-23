import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

configure({ asyncUtilTimeout: 3000 })

const storageValues = new Map()
Object.defineProperty(window, 'localStorage', {
  configurable: true,
  value: {
    clear: () => storageValues.clear(),
    getItem: (key) => storageValues.get(String(key)) ?? null,
    key: (index) => Array.from(storageValues.keys())[index] ?? null,
    get length() { return storageValues.size },
    removeItem: (key) => storageValues.delete(String(key)),
    setItem: (key, value) => storageValues.set(String(key), String(value)),
  },
})

afterEach(() => {
  cleanup()
  document.body.innerHTML = ''
  document.documentElement.className = ''
  document.querySelectorAll('[data-test-style]').forEach((element) => element.remove())
})
