import { act, render, screen, within } from '@testing-library/react'
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

  it('downloads a recording through the authenticated API client', async () => {
    const user = userEvent.setup()
    const createObjectURL = vi.fn(() => 'blob:recording')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectURL,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectURL,
    })
    apiClient.get.mockImplementation((endpoint) => {
      if (endpoint === '/api/admin/live/recordings/3/download') {
        return Promise.resolve({
          data: new Blob(['recording']),
          headers: { 'content-disposition': 'attachment; filename="live.mp4"' },
        })
      }
      return Promise.resolve({ data: responses[endpoint] })
    })

    render(<AdminLivePage />)
    await user.click(await screen.findByRole('button', { name: '播放录像 第 1 场.mp4' }))
    expect(document.querySelector('video[aria-label="播放录像 第 1 场.mp4"]')).toHaveAttribute(
      'src',
      'blob:recording',
    )
    await user.click(screen.getByRole('button', { name: '关闭' }))
    await user.click(await screen.findByRole('button', { name: '下载录像 第 1 场.mp4' }))

    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/admin/live/recordings/3/download',
      { responseType: 'blob' },
    )
    expect(createObjectURL).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:recording')
  })

  it('submits streamer quality, bitrate and latency settings', async () => {
    const user = userEvent.setup()
    apiClient.put.mockResolvedValue({ data: settings })

    render(<AdminLivePage />)

    await user.clear(await screen.findByLabelText('目标码率（kbps）'))
    await user.type(screen.getByLabelText('目标码率（kbps）'), '5800')
    await user.selectOptions(screen.getByLabelText('推流画质'), 'clear')
    await user.selectOptions(screen.getByLabelText('直播延时'), 'ultra_low')
    await user.click(screen.getByRole('button', { name: '保存设置' }))

    expect(apiClient.put).toHaveBeenCalledWith(
      API_ENDPOINTS.ADMIN_LIVE_SETTINGS,
      expect.objectContaining({
        stream_quality: 'clear',
        target_bitrate_kbps: 5800,
        latency_mode: 'ultra_low',
      }),
    )
  })

  it('submits the automatic recording switch with its safety explanation', async () => {
    const user = userEvent.setup()
    apiClient.put.mockResolvedValue({ data: settings })
    render(<AdminLivePage />)

    expect(await screen.findByText('当前在线：2 人')).toBeInTheDocument()
    expect(screen.getByText(/最近刷新：/)).toBeInTheDocument()
    const recordingToggle = await screen.findByLabelText('自动录制直播')
    expect(recordingToggle).toBeChecked()
    expect(screen.getByText(/关闭后当前和后续直播都不会自动录像/)).toBeInTheDocument()
    expect(screen.getByText(/磁盘空间不足时会自动暂停/)).toBeInTheDocument()

    await user.click(recordingToggle)
    await user.click(screen.getByRole('button', { name: '保存设置' }))

    expect(apiClient.put).toHaveBeenCalledWith(
      API_ENDPOINTS.ADMIN_LIVE_SETTINGS,
      expect.objectContaining({ recording_enabled: false }),
    )
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

    expect(await screen.findByText('当前没有人观看直播。')).toBeInTheDocument()
  })
})
