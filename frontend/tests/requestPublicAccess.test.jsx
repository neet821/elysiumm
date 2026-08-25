import { beforeEach, describe, expect, it, vi } from 'vitest'

const responseRejected = vi.hoisted(() => ({ handler: null }))

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn((_fulfilled, rejected) => { responseRejected.handler = rejected }) },
      },
    })),
    post: vi.fn(),
  },
}))

import apiClient from '../src/utils/request.js'

describe('public access request handling', () => {
  beforeEach(() => {
    localStorage.clear()
    window.history.replaceState({}, '', '/live')
  })

  it('does not redirect or clear the session for an expected public 401', async () => {
    localStorage.setItem('token', 'still-valid-for-other-pages')
    const error = {
      config: { url: '/api/live/session', method: 'post', skipAuthRedirect: true, _retry: true },
      response: { status: 401, data: { detail: '需要登录后观看' } },
    }

    await expect(responseRejected.handler(error)).rejects.toBe(error)
    expect(localStorage.getItem('token')).toBe('still-valid-for-other-pages')
    expect(window.location.pathname).toBe('/live')
    expect(apiClient).toBeDefined()
  })
})
