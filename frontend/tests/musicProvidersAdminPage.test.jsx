import { act, render, screen } from '@testing-library/react'
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

describe('root-managed shared music provider status', () => {
  beforeEach(() => {
    apiClient.get.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows status and does not expose a web login or unlink action', async () => {
    apiClient.get.mockResolvedValue({ data: providerStatus })

    render(<MusicProvidersAdminPage />)
    await act(async () => {})
    expect(screen.getAllByText(/凭据轮换由运维流程执行/)).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /重新登录/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /退出/ })).not.toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.MUSIC_PROVIDER_STATUS)
  })
})
