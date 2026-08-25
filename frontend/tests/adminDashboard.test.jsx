import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn() },
}))

import { API_ENDPOINTS } from '../src/config.js'
import AdminOverviewPage from '../src/pages/AdminOverviewPage.jsx'
import AdminRoomsPage from '../src/pages/AdminRoomsPage.jsx'
import AdminSecurityPage from '../src/pages/AdminSecurityPage.jsx'
import apiClient from '../src/utils/request.js'

const overview = {
  generated_at: '2026-07-16T08:00:00Z',
  health: { status: 'ok', database: 'connected', storage: 'database metadata available' },
  users: { total: 12, active: 10, inactive: 2, administrators: 2 },
  rooms: { media_active: 2, game_active: 1 },
  files: { manual_count: 3, manual_bytes: 1024, synced_count: 2, synced_bytes: 2048, active_uploads: 1 },
  sync: { devices: 2, online: 1, paused: 0, revoked: 1, expired: 0 },
  books: { total: 4, published: 3, lists: 2 },
  backups: { jobs: 1, latest_status: 'completed', latest_created_at: '2026-07-16T07:00:00Z' },
  recent_failures: [{ id: 9, actor_username: 'admin', action: 'upload_rejected', resource_type: 'sync', resource_id: '7', outcome: 'failed', created_at: '2026-07-16T07:30:00Z' }],
}

const security = {
  generated_at: '2026-07-16T08:00:00Z',
  counts: { inactive_users: 2, revoked_devices: 1, expired_devices: 3, admin_failed: 4, admin_rate_limited: 5, realtime_failed: 6, realtime_rate_limited: 7 },
  configuration: { socket_auth_required: true, cors_credentials_enabled: true, cors_allowed_origin_count: 2, cors_wildcard_configured: false },
  capabilities: { web_session_inventory_available: false, web_session_inventory_reason: '此应用不会在服务端持久保存网页会话。' },
  admin_audit: [{ id: 1, actor_username: 'admin', action: 'device_rotate', resource_type: 'sync_device', resource_id: '4', outcome: 'success', created_at: '2026-07-16T07:20:00Z' }],
  realtime_audit: [{ id: 2, actor_username: 'member', event_name: 'join_game_room', room_id: 8, outcome: 'rate_limited', created_at: '2026-07-16T07:25:00Z' }],
}

function renderPage(Page) {
  return render(<MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}><Page /></MemoryRouter>)
}

describe('administrator overview and security evidence', () => {
  beforeEach(() => {
    apiClient.get.mockReset()
  })

  it('loads the truthful overview and exposes a retryable summary', async () => {
    apiClient.get.mockResolvedValue({ data: overview })
    renderPage(AdminOverviewPage)

    expect(screen.getByRole('status', { name: '正在载入管理总览' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '控制台总览' })).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_OVERVIEW)
    for (const text of ['12 位用户', '3 个活跃房间', '5 个受管文件', '2 台同步设备']) {
      expect(screen.getAllByText(text).length).toBeGreaterThan(0)
    }
    for (const [name, href] of [['用户', '/admin/users'], ['房间', '/admin/rooms'], ['文件', '/admin/files'], ['服务器状态', '/admin/services'], ['曲库账户', '/admin/music'], ['直播', '/admin/live']]) {
      expect(screen.getByRole('link', { name: new RegExp(name) })).toHaveAttribute('href', href)
    }
    expect(screen.getByText('上传被拒绝')).toBeInTheDocument()
    expect(screen.getAllByText('数据库：已连接').length).toBeGreaterThan(0)
  })

  it('shows only generic overview errors and can retry in place', async () => {
    const user = userEvent.setup()
    apiClient.get
      .mockRejectedValueOnce(new Error('database password at /private/path'))
      .mockResolvedValueOnce({ data: {} })
      .mockResolvedValueOnce({ data: overview })
      .mockResolvedValueOnce({ data: {} })
    renderPage(AdminOverviewPage)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('管理总览暂时无法载入。')
    expect(alert).not.toHaveTextContent('password')
    await user.click(screen.getByRole('button', { name: '重新载入管理总览' }))
    expect(await screen.findByText('12 位用户')).toBeInTheDocument()
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
    expect(screen.getByText('加入桌游房')).toBeInTheDocument()
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

  it('adds the safe game-room aggregate to the existing media room administration', async () => {
    apiClient.get.mockImplementation((endpoint) => {
      if (endpoint === API_ENDPOINTS.ADMIN_ROOMS) return Promise.resolve({ data: { rooms: [], total: 0 } })
      if (endpoint === API_ENDPOINTS.ADMIN_OVERVIEW) return Promise.resolve({ data: { rooms: { game_active: 2 } } })
      return Promise.reject(new Error('unexpected endpoint'))
    })
    const styles = { bg: '', bgSecondary: '', border: '', text: '', textMuted: '', accentClass: '' }
    render(<MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}><AdminRoomsPage styles={styles} isDark={false} /></MemoryRouter>)

    expect(await screen.findByText('2 个活跃游戏房 · 0 个活跃媒体房')).toBeInTheDocument()
  })
})
