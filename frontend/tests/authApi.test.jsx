import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import apiClient from '../src/utils/request'
import { API_ENDPOINTS } from '../src/config'
import {
  fetchCurrentUser,
  loginWithPassword,
  logoutCurrentSession,
  registerAccount,
} from '../src/features/auth/authApi'

describe('auth API transport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches the current user through the existing endpoint', async () => {
    apiClient.get.mockResolvedValue({ data: { id: 7 } })

    const response = await fetchCurrentUser()

    expect(response.data).toEqual({ id: 7 })
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.USER_INFO)
  })

  it('registers with the existing JSON payload', async () => {
    await registerAccount('alice', 'alice@example.test', 'secret')

    expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.REGISTER, {
      username: 'alice',
      email: 'alice@example.test',
      password: 'secret',
    })
  })

  it('logs in with browser-generated multipart form data', async () => {
    await loginWithPassword('alice', 'secret')

    const [url, body] = apiClient.post.mock.calls[0]
    expect(url).toBe(API_ENDPOINTS.LOGIN)
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('username')).toBe('alice')
    expect(body.get('password')).toBe('secret')
  })

  it('logs out through the existing endpoint', async () => {
    await logoutCurrentSession()

    expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.LOGOUT)
  })
})
