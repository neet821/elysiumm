import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('../src/features/live/LivePlayer.jsx', () => ({
  default: ({ mediaUrl, minimal }) => (
    <div className={minimal ? 'live-player live-player--minimal' : 'live-player'} data-media-url={mediaUrl || ''}>
      <video aria-label="直播播放器" data-media-url={mediaUrl || ''} />
      {minimal && <div aria-label="直播播放控件" />}
    </div>
  ),
}))

vi.mock('../src/pages/AdminLivePage.jsx', () => ({
  default: () => <div data-testid="inline-admin-live" />,
}))

const optionalAuthState = vi.hoisted(() => ({ isAdmin: true, loading: false }))

vi.mock('../src/contexts/AuthContext', () => ({
  useOptionalAuth: () => optionalAuthState,
}))

import { API_ENDPOINTS } from '../src/config.js'
import LivePage from '../src/pages/LivePage.jsx'
import apiClient from '../src/utils/request.js'


const liveStatus = {
  status: 'live',
  title: '今晚直播',
  description: '和 Blue Album 一起看。',
  access_mode: 'invite',
  started_at: '2026-07-28T08:00:00Z',
}


describe('public live page', () => {
  beforeEach(() => {
    apiClient.get.mockReset()
    apiClient.post.mockReset()
    optionalAuthState.isAdmin = false
    optionalAuthState.loading = false
    window.history.replaceState({}, '', '/live')
    Object.defineProperty(navigator, 'sendBeacon', {
      configurable: true,
      value: vi.fn(() => true),
    })
  })

  it('exchanges an invite once, removes it from the address and shows the player', async () => {
    window.history.replaceState({}, '', '/live?invite=secret-invite')
    apiClient.get.mockResolvedValue({ data: liveStatus })
    apiClient.post.mockResolvedValue({
      data: {
        viewer_session_id: 'viewer-1',
        media_url: '/live-media/live/stream/index.m3u8',
        expires_in: 120,
      },
    })

    render(<LivePage />)

    expect(await screen.findByRole('heading', { name: '今晚直播' })).toBeInTheDocument()
    expect(apiClient.post).toHaveBeenCalledWith(
      API_ENDPOINTS.LIVE_SESSION,
      { invite_token: 'secret-invite' },
      { skipAuthRedirect: true },
    )
    expect(window.location.search).toBe('')
    expect(screen.getByLabelText('直播播放器')).toHaveAttribute(
      'data-media-url',
      '/live-media/live/stream/index.m3u8',
    )
  })

  it('shows an empty centered player with a not-started prompt', async () => {
    apiClient.get.mockResolvedValue({
      data: {
        ...liveStatus,
        status: 'waiting',
        access_mode: 'public',
      },
    })

    render(<LivePage />)

    expect(await screen.findByText('未开播')).toBeInTheDocument()
    expect(screen.getByLabelText('直播播放器')).toHaveAttribute('data-media-url', '')
    expect(screen.getByLabelText('直播播放控件')).toBeInTheDocument()
    expect(screen.queryByText('等待开播')).not.toBeInTheDocument()
    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it('keeps the empty player for a completed broadcast without a state overlay', async () => {
    apiClient.get.mockResolvedValue({
      data: {
        ...liveStatus,
        status: 'ended',
      },
    })

    render(<LivePage />)

    expect(await screen.findByText('未开播')).toBeInTheDocument()
    expect(screen.getByLabelText('直播播放器')).toHaveAttribute('data-media-url', '')
    expect(screen.queryByText('直播已结束')).not.toBeInTheDocument()
    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it.each([
    ['邀请链接已失效', 403, '邀请链接已失效'],
    ['你没有观看权限', 403, '你没有观看权限'],
    ['需要登录后观看', 401, '登录后即可观看'],
  ])('renders a bounded access error for %s', async (detail, status, message) => {
    apiClient.get.mockResolvedValue({ data: liveStatus })
    apiClient.post.mockRejectedValue({
      response: { status, data: { detail } },
    })

    render(<LivePage />)

    expect(await screen.findByText(message)).toBeInTheDocument()
    expect(screen.queryByLabelText('直播播放器')).not.toBeInTheDocument()
  })

  it('shows a retryable service message without leaking request details', async () => {
    apiClient.get.mockRejectedValue(
      new Error('upstream failed at /private/media/path'),
    )

    render(<LivePage />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('直播服务暂时不可用')
    expect(alert).not.toHaveTextContent('/private/media/path')
    await waitFor(() => {
      expect(screen.queryByLabelText('直播播放器')).not.toBeInTheDocument()
    })
  })

  it('keeps the live page usable when browser storage is unavailable', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Storage is unavailable', 'SecurityError')
    })
    apiClient.get.mockResolvedValue({ data: liveStatus })
    apiClient.post.mockResolvedValue({
      data: {
        viewer_session_id: 'viewer-1',
        media_url: '/live-media/live/stream/index.m3u8',
        expires_in: 120,
      },
    })

    render(<LivePage />)

    expect(await screen.findByRole('heading', { name: '今晚直播' })).toBeInTheDocument()
    expect(screen.queryByText('正在直播')).not.toBeInTheDocument()
    expect(screen.queryByText('直播中')).not.toBeInTheDocument()
    expect(screen.queryByText('画面延迟目标约')).not.toBeInTheDocument()
    expect(screen.getByLabelText('直播播放控件')).toBeInTheDocument()
    expect(screen.getByLabelText('直播留言')).toBeInTheDocument()
    expect(screen.getByLabelText('直播留言').querySelector('ul').nextElementSibling.tagName).toBe('FORM')
    getItem.mockRestore()
  })

  it('opens the administrator workspace directly without starting the public live session', async () => {
    optionalAuthState.isAdmin = true
    render(<LivePage />)

    expect(screen.getByTestId('inline-admin-live')).toBeInTheDocument()
    expect(screen.queryByText('直播已结束')).not.toBeInTheDocument()
    expect(apiClient.get).not.toHaveBeenCalled()
  })

  it('opens the public minimal watch page for an administrator watch link', async () => {
    optionalAuthState.isAdmin = true
    window.history.replaceState({}, '', '/live?watch=1')
    apiClient.get.mockResolvedValue({ data: liveStatus })
    apiClient.post.mockResolvedValue({
      data: {
        viewer_session_id: 'viewer-1',
        media_url: '/live-media/live/stream/index.m3u8',
        expires_in: 120,
      },
    })

    render(<LivePage />)

    expect(await screen.findByLabelText('直播播放器')).toBeInTheDocument()
    expect(screen.queryByTestId('inline-admin-live')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('直播留言')).not.toBeInTheDocument()
    expect(screen.queryByText('直播中')).not.toBeInTheDocument()
  })

  it('keeps the public live route free of the administrator workspace for regular users', async () => {
    optionalAuthState.isAdmin = false
    apiClient.get.mockResolvedValue({ data: { ...liveStatus, status: 'ended' } })

    render(<LivePage />)

    expect(await screen.findByText('未开播')).toBeInTheDocument()
    expect(screen.queryByTestId('inline-admin-live')).not.toBeInTheDocument()
  })

  it('shows only the centered not-started state on the administrator watch page', async () => {
    optionalAuthState.isAdmin = true
    window.history.replaceState({}, '', '/live?watch=1')
    apiClient.get.mockResolvedValue({ data: { ...liveStatus, status: 'ended' } })

    render(<LivePage />)

    expect(await screen.findByText('未开播')).toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveClass('live-watch-page')
    expect(screen.queryByText('直播已结束')).not.toBeInTheDocument()
    expect(screen.queryByText('感谢观看，下一次开播时这里会出现新的画面。')).not.toBeInTheDocument()
  })

  it('lets viewers set a nickname and send a live message', async () => {
    const user = userEvent.setup()
    apiClient.get.mockResolvedValue({ data: liveStatus })
    apiClient.post
      .mockResolvedValueOnce({
        data: {
          viewer_session_id: 'viewer-1',
          media_url: '/live-media/live/stream/index.m3u8',
          expires_in: 120,
        },
      })
      .mockResolvedValueOnce({
        data: {
          id: 1,
          live_session_id: 3,
          viewer_session_id: 'viewer-1',
          nickname: '小蓝',
          content: '开播啦',
          created_at: '2026-07-28T08:00:00Z',
        },
      })

    render(<LivePage />)

    await screen.findByLabelText('直播播放器')
    await user.type(screen.getByLabelText('昵称'), '小蓝')
    await user.type(screen.getByLabelText('留言内容'), '开播啦')
    await user.click(screen.getByRole('button', { name: '发送留言' }))

    expect(apiClient.post).toHaveBeenCalledWith(
      API_ENDPOINTS.LIVE_MESSAGES,
      {
        nickname: '小蓝',
        content: '开播啦',
      },
      { skipAuthRedirect: true },
    )
  })
})
