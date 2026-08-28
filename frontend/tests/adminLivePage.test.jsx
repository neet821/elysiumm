import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: {
    delete: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

vi.mock('../src/features/live/useLiveSession.js', () => ({
  default: () => ({
    mediaUrl: '/live-media/live/stream/index.m3u8',
    retry: vi.fn(),
    state: 'live',
    status: { title: '今晚直播' },
  }),
}))

vi.mock('../src/features/live/LivePlayer.jsx', () => ({
  default: ({ mediaUrl }) => <div data-testid="admin-live-preview" data-media-url={mediaUrl} />,
}))

vi.mock('../src/features/live/LiveMessageBoard.jsx', () => ({
  default: () => <section aria-label="直播留言" data-testid="admin-live-messages" />,
}))

import { API_ENDPOINTS } from '../src/config.js'
import AdminLivePage from '../src/pages/AdminLivePage.jsx'
import apiClient from '../src/utils/request.js'


const settings = {
  id: 1,
  title: '今晚直播',
  description: '测试',
  cover_url: null,
  access_mode: 'public',
  viewing_enabled: true,
  recording_enabled: true,
  stream_quality: 'balanced',
  target_bitrate_kbps: 4200,
  latency_mode: 'low',
  revision: 3,
  stream_key_hint: 'old123',
  rtmp_server: 'rtmp://8.148.83.28/live',
}

const audience = [{
  id: 'viewer-1',
  live_session_id: 9,
  user_id: 2,
  username: 'member',
  email: 'member@example.com',
  ip_address: '203.0.113.8',
  country: '中国',
  region: '上海市',
  city: '上海市',
  device_type: 'mobile',
  operating_system: 'Android',
  browser: 'Chrome',
  first_seen_at: '2026-07-28T08:00:00Z',
  last_seen_at: '2026-07-28T08:12:30Z',
  watched_seconds: 750,
  ended_at: null,
}, {
  id: 'viewer-2',
  live_session_id: 9,
  user_id: null,
  username: null,
  email: null,
  ip_address: '198.51.100.20',
  country: '中国',
  region: '广东省',
  city: '广州市',
  device_type: 'computer',
  operating_system: 'Linux',
  browser: 'Firefox',
  first_seen_at: '2026-07-28T08:10:00Z',
  last_seen_at: '2026-07-28T08:12:00Z',
  watched_seconds: 120,
  ended_at: null,
}]

const responses = {
  [API_ENDPOINTS.ADMIN_LIVE_SETTINGS]: settings,
  [API_ENDPOINTS.ADMIN_LIVE_STATUS]: {
    is_live: true,
    active_viewers: 1,
    session: {
      id: 9,
      status: 'live',
      started_at: '2026-07-28T08:00:00Z',
      width: 1920,
      height: 1080,
      frame_rate: 30,
      bit_rate: 4500000,
      video_codec: 'H264',
      audio_codec: 'AAC',
    },
  },
  [API_ENDPOINTS.ADMIN_LIVE_ALLOWED_USERS]: [],
  [API_ENDPOINTS.ADMIN_LIVE_INVITES]: [],
  [API_ENDPOINTS.ADMIN_LIVE_AUDIENCE]: audience,
  [API_ENDPOINTS.ADMIN_LIVE_AUDIENCE_HISTORY]: [
    {
      ...audience[0],
      live_session_id: 8,
      id: 'viewer-history-1',
      first_seen_at: '2026-07-27T08:00:00Z',
      ended_at: '2026-07-27T08:20:00Z',
    },
  ],
  [API_ENDPOINTS.ADMIN_LIVE_SESSIONS]: [],
  [API_ENDPOINTS.ADMIN_LIVE_RECORDINGS]: [{
    id: 3,
    display_name: '第 1 场.mp4',
    file_size: 1024,
    duration_seconds: 60,
    status: 'ready',
    download_url: '/api/admin/live/recordings/3/download',
  }],
  [API_ENDPOINTS.ADMIN_USERS]: [],
}


describe('live administrator workspace', () => {
  beforeEach(() => {
    for (const method of ['get', 'post', 'put', 'delete']) {
      apiClient[method].mockReset()
    }
    apiClient.get.mockImplementation((endpoint) => (
      Promise.resolve({ data: responses[endpoint] })
    ))
  })

  it('embeds the preview and keeps the administrator workspace focused', async () => {
    render(<AdminLivePage />)

    expect(await screen.findByTestId('admin-live-preview')).toHaveAttribute(
      'data-media-url',
      '/live-media/live/stream/index.m3u8',
    )
    expect(screen.queryByRole('heading', { name: '直播' })).not.toBeInTheDocument()
    expect(screen.queryByText('直播管理')).not.toBeInTheDocument()
    expect(screen.queryByText('单直播间')).not.toBeInTheDocument()
    expect(screen.queryByText('设置 OBS、观看权限、访客记录和自动录像。')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /打开观看页/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /刷新直播管理信息/ })).not.toBeInTheDocument()
    expect(screen.queryByText('自动录像')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('直播标题')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('直播简介')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('目标码率（kbps）')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('封面地址')).not.toBeInTheDocument()
    expect(await screen.findByLabelText('OBS 服务器')).toBeInTheDocument()
    expect(await screen.findByLabelText('OBS 当前密钥')).toBeInTheDocument()
    expect(screen.getByText('直播场次')).toBeInTheDocument()
    expect(screen.queryByRole('row', { name: /203\.0\.113\.8/ })).not.toBeInTheDocument()
    expect(screen.queryByText('开始时间')).not.toBeInTheDocument()
    expect(screen.queryByText('画面')).not.toBeInTheDocument()
    expect(screen.queryByText('编码')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '清除记录' })).not.toBeInTheDocument()
  })

  it('puts the back control in the player and keeps read-only panels directly below it', async () => {
    render(<AdminLivePage />)

    expect(await screen.findByTestId('admin-live-preview')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '返回首页' })).not.toBeInTheDocument()
    expect(document.querySelector('.admin-live__preview-back')).not.toBeInTheDocument()
    expect(screen.queryByText('当前状态')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '留言' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('管理员直播留言')).toBeInTheDocument()
    expect(screen.getByText('在线人数')).toBeInTheDocument()
  })

  it('opens historical viewing records from the audience secondary menu', async () => {
    const user = userEvent.setup()
    render(<AdminLivePage />)

    await user.click(await screen.findByRole('button', { name: /观看人数：1/ }))
    expect(await screen.findByText('历史观看')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: '历史观看' }))
    expect(await screen.findByText(/2026[/-]7[/-]27/)).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(
      API_ENDPOINTS.ADMIN_LIVE_AUDIENCE_HISTORY,
      { params: { limit: 200, session_id: 9 } },
    )
  })

  it('exposes a custom live title field in the start settings', async () => {
    render(<AdminLivePage />)

    expect(await screen.findByLabelText('直播名称')).toHaveValue('今晚直播')
  })

  it('places settings before the read-only audience and message panels', async () => {
    render(<AdminLivePage />)

    const preview = await screen.findByLabelText('直播预览')
    const settings = await screen.findByRole('heading', { name: '开播设置' })
    const belowPreview = settings.closest('.admin-live__grid').nextElementSibling
    expect(belowPreview).toHaveClass('admin-live__below-preview')
    expect(belowPreview.firstElementChild).toHaveClass('admin-live__admin-messages')
    expect(belowPreview.lastElementChild).toHaveClass('admin-live__audience-card')
    expect(preview.compareDocumentPosition(settings) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByTestId('admin-live-messages')).toBeInTheDocument()
    expect(screen.queryByText('当前状态')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '留言' })).not.toBeInTheDocument()
  })

  it('places live sessions beside opening settings on desktop', async () => {
    render(<AdminLivePage />)

    const settingsCard = (await screen.findByRole('heading', { name: '开播设置' })).closest('section')
    const sessionsCard = screen.getByText('直播场次').closest('details')

    expect(settingsCard.parentElement).toHaveClass('admin-live__grid')
    expect(sessionsCard).toHaveClass('admin-live__card--sessions')
    expect(sessionsCard).not.toHaveClass('admin-live__card--wide')
  })

  it('uses concrete administrator recording endpoints', () => {
    expect(API_ENDPOINTS.ADMIN_LIVE_RECORDINGS).toBe(
      `${window.location.origin}/api/admin/live/recordings`,
    )
    expect(API_ENDPOINTS.ADMIN_LIVE_RECORDING(3)).toBe(
      `${window.location.origin}/api/admin/live/recordings/3`,
    )
  })

  it('keeps a rotated secret one-time and confirms the destructive action', async () => {
    const user = userEvent.setup()
    apiClient.post.mockResolvedValue({
      data: {
        stream_key: 'new-secret',
        obs_stream_key: 'stream?token=new-secret',
        stream_key_hint: 'secret',
        rtmp_server: 'rtmp://8.148.83.28/live',
      },
    })
    render(<AdminLivePage />)

    await user.click(await screen.findByRole('button', { name: '更换推流密钥' }))
    expect(screen.getByRole('dialog', { name: '确认更换推流密钥' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '确认更换' }))

    expect(await screen.findByText(/仅显示这一次/)).toBeInTheDocument()
    expect(screen.getByLabelText('OBS 推流密钥')).toHaveValue(
      'stream?token=new-secret',
    )
    await user.click(screen.getByRole('button', { name: '关闭' }))
    expect(screen.queryByDisplayValue(/new-secret/)).not.toBeInTheDocument()
  })

  it('shows visitor region, device, browser and watch time without storage paths', async () => {
    render(<AdminLivePage />)

    await userEvent.setup().click(await screen.findByRole('button', { name: /观看人数：1/ }))
    const row = await screen.findByRole('row', { name: /203\.0\.113\.8/ })
    expect(within(row).getByText('member')).toBeInTheDocument()
    expect(within(row).getByText('member@example.com')).toBeInTheDocument()
    expect(within(row).getByText('用户 #2')).toBeInTheDocument()
    expect(within(row).getByText('中国 · 上海市 · 上海市')).toBeInTheDocument()
    expect(within(row).getByText('手机 · Android · Chrome')).toBeInTheDocument()
    expect(within(row).getByText('12 分 30 秒')).toBeInTheDocument()
    expect(within(row).getByText(/进入：/)).toBeInTheDocument()
    expect(within(row).getByText(/最后活动：/)).toBeInTheDocument()
    const anonymousRow = screen.getByRole('row', { name: /198\.51\.100\.20/ })
    expect(within(anonymousRow).getByText('未登录访客')).toBeInTheDocument()
    expect(within(anonymousRow).getByText('中国 · 广东省 · 广州市')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '地区数据由 DB-IP 提供' })).toHaveAttribute(
      'href',
      'https://db-ip.com',
    )
    expect(document.body).not.toHaveTextContent('/srv/blue-live/recordings')
  })

  it('does not expose automatic recording controls', async () => {
    render(<AdminLivePage />)
    expect(await screen.findByText('开播设置')).toBeInTheDocument()
    expect(screen.queryByText('录像')).not.toBeInTheDocument()
    expect(screen.queryByText('自动录制直播')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /播放录像/ })).not.toBeInTheDocument()
  })

  it('keeps the compact settings focused on viewing and OBS', async () => {
    render(<AdminLivePage />)

    const viewerToggle = await screen.findByLabelText('观看人数：1')
    expect(viewerToggle).toBeInTheDocument()
    await userEvent.setup().click(viewerToggle)
    expect(await screen.findByText('当前在线：2 人')).toBeInTheDocument()
    expect(screen.queryByLabelText('自动录制直播')).not.toBeInTheDocument()
    expect(screen.queryByText(/磁盘空间不足时会自动暂停/)).not.toBeInTheDocument()
  })

  it('keeps the last audience visible when an automatic refresh fails', async () => {
    vi.useFakeTimers()
    let audienceRequests = 0
    apiClient.get.mockImplementation((endpoint) => {
      if (endpoint === API_ENDPOINTS.ADMIN_LIVE_AUDIENCE) {
        audienceRequests += 1
        if (audienceRequests > 2) return Promise.reject(new Error('offline'))
      }
      return Promise.resolve({ data: responses[endpoint] })
    })

    const view = render(<AdminLivePage />)
    await act(async () => {})
    fireEvent.click(screen.getByLabelText('观看人数：1'))
    expect(screen.getByRole('row', { name: /203\.0\.113\.8/ })).toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })

    expect(screen.getByText('在线观众刷新失败。')).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /203\.0\.113\.8/ })).toBeInTheDocument()
    view.unmount()
    vi.useRealTimers()
  })

  it('shows a clear empty state when nobody is watching', async () => {
    apiClient.get.mockImplementation((endpoint) => Promise.resolve({
      data: endpoint === API_ENDPOINTS.ADMIN_LIVE_AUDIENCE ? [] : responses[endpoint],
    }))

    render(<AdminLivePage />)

    fireEvent.click(await screen.findByLabelText('观看人数：1'))
    expect(await screen.findByText('当前没有人观看直播。')).toBeInTheDocument()
  })
})
