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
  default: ({ mediaUrl }) => (
    <video aria-label="直播播放器" data-media-url={mediaUrl} />
  ),
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
    )
    expect(window.location.search).toBe('')
    expect(screen.getByLabelText('直播播放器')).toHaveAttribute(
      'data-media-url',
      '/live-media/live/stream/index.m3u8',
    )
  })

  it('shows the waiting state without mounting a black video element', async () => {
    apiClient.get.mockResolvedValue({
      data: {
        ...liveStatus,
        status: 'waiting',
        access_mode: 'public',
      },
    })

    render(<LivePage />)

    expect(await screen.findByText('等待开播')).toBeInTheDocument()
    expect(screen.queryByLabelText('直播播放器')).not.toBeInTheDocument()
    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it('shows a final ended state without reconnecting after a completed broadcast', async () => {
    apiClient.get.mockResolvedValue({
      data: {
        ...liveStatus,
        status: 'ended',
      },
    })

    render(<LivePage />)

    expect(await screen.findByText('直播已结束')).toBeInTheDocument()
    expect(screen.queryByLabelText('直播播放器')).not.toBeInTheDocument()
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
    )
  })
})
