import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: {
    delete: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import { API_ENDPOINTS } from '../src/config.js'
import MusicProvidersAdminPage from '../src/pages/MusicProvidersAdminPage.jsx'
import apiClient from '../src/utils/request.js'


const providerStatus = {
  service_available: true,
  providers: {
    netease: { configured: false, status: 'missing', checked_at: '2026-08-17T00:00:00Z' },
    qq: { configured: false, status: 'missing', checked_at: '2026-08-17T00:00:00Z' },
  },
}

describe('shared music provider login', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    apiClient.delete.mockReset()
    apiClient.get.mockReset()
    apiClient.post.mockReset()
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:netease-login')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('continues checking the NetEase login after the QR image appears', async () => {
    const sessionId = 'netease-session-1'
    let loginChecks = 0
    apiClient.get.mockImplementation((endpoint) => {
      if (endpoint === API_ENDPOINTS.MUSIC_PROVIDER_STATUS) {
        return Promise.resolve({ data: providerStatus })
      }
      if (endpoint === API_ENDPOINTS.MUSIC_PROVIDER_LOGIN_IMAGE('netease', sessionId)) {
        return Promise.resolve({ data: new Blob(['qr'], { type: 'image/png' }) })
      }
      if (endpoint === API_ENDPOINTS.MUSIC_PROVIDER_LOGIN_STATUS('netease', sessionId)) {
        loginChecks += 1
        return Promise.resolve({
          data: loginChecks === 1
            ? { session_id: sessionId, provider: 'netease', status: 'pending', message: '请扫码' }
            : { session_id: sessionId, provider: 'netease', status: 'ready', message: '网易云共享账号已登录' },
        })
      }
      return Promise.reject(new Error(`Unexpected endpoint: ${endpoint}`))
    })
    apiClient.post.mockResolvedValue({
      data: { session_id: sessionId, provider: 'netease', status: 'pending', message: '请扫码' },
    })

    render(<MusicProvidersAdminPage />)
    await act(async () => {})
    fireEvent.click(screen.getAllByRole('button', { name: /重新登录/ })[0])
    await act(async () => {})

    expect(screen.getByRole('img', { name: '登录二维码' })).toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600)
    })

    expect(screen.getByText(/网易云共享账号已登录/)).toBeInTheDocument()
  })
})
