import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn() },
}))

import { API_ENDPOINTS } from '../src/config.js'
import AdminRoomsPage from '../src/pages/AdminRoomsPage.jsx'
import AdminSecurityPage from '../src/pages/AdminSecurityPage.jsx'
import apiClient from '../src/utils/request.js'

const security = {
  generated_at: '2026-07-16T08:00:00Z',
  counts: { inactive_users: 2, revoked_devices: 1, expired_devices: 3, admin_failed: 4, admin_rate_limited: 5, realtime_failed: 6, realtime_rate_limited: 7 },
  configuration: { socket_auth_required: true, cors_credentials_enabled: true, cors_allowed_origin_count: 2, cors_wildcard_configured: false },
  capabilities: { web_session_inventory_available: false, web_session_inventory_reason: '此应用不会在服务端持久保存网页会话。' },
  admin_audit: [{ id: 1, actor_username: 'admin', action: 'device_rotate', resource_type: 'sync_device', resource_id: '4', outcome: 'success', created_at: '2026-07-16T07:20:00Z' }],
  realtime_audit: [{ id: 2, actor_username: 'member', event_name: 'join_room', room_id: 8, outcome: 'rate_limited', created_at: '2026-07-16T07:25:00Z' }],
}

function renderPage(Page) {
  return render(<MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}><Page /></MemoryRouter>)
}

describe('administrator overview and security evidence', () => {
  beforeEach(() => {
    apiClient.get.mockReset()
  })

  it('renders bounded security evidence and states the missing session capability honestly', async () => {
    apiClient.get.mockResolvedValue({ data: security })
    renderPage(AdminSecurityPage)

    expect(await screen.findByRole('heading', { name: '安全记录' })).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_SECURITY, { params: { limit: 50 } })
    expect(screen.getByText('此应用不会在服务端持久保存网页会话。')).toBeInTheDocument()
    expect(screen.getByText('实时连接验证：必须')).toBeInTheDocument()
    expect(screen.getByText('CORS 通配来源：未配置')).toBeInTheDocument()
    expect(screen.getByText('更新设备凭据')).toBeInTheDocument()
    expect(screen.getByText('加入房间')).toBeInTheDocument()
    expect(screen.getByText('5 次管理员操作限速')).toBeInTheDocument()
    expect(screen.getByText('7 次实时操作限速')).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('session_count')
  })

  it('does not surface internal security request errors', async () => {
    apiClient.get.mockRejectedValue(new Error('socket secret'))
    renderPage(AdminSecurityPage)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('安全记录暂时无法载入。'))
    expect(document.body.textContent).not.toContain('socket secret')
  })

  it('shows only the media room aggregate in room administration', async () => {
    apiClient.get.mockResolvedValue({ data: { rooms: [], total: 0 } })
    const styles = { bg: '', bgSecondary: '', border: '', text: '', textMuted: '', accentClass: '' }
    render(<MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}><AdminRoomsPage styles={styles} isDark={false} /></MemoryRouter>)

    expect(await screen.findByText('0 个活跃媒体房')).toBeInTheDocument()
  })
})
