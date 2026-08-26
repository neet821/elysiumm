import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

const roomState = {
  buffers: {},
  currentItem: null,
  leave: vi.fn(),
  localReady: {},
  members: [{ is_online: true, user_id: 1, username: 'host' }],
  messages: [{ id: 1, message: '你好', username: 'host' }],
  notice: '',
  requestSnapshot: vi.fn(),
  room: {
    control_mode: 'host_only',
    host_user_id: 1,
    id: 9,
    room_code: 'ROOM09',
    room_name: '测试视频房',
  },
  sendMessage: vi.fn(),
  snapshot: null,
  syncStatus: 'synced',
}

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ loading: false, user: { id: 1, role: 'user' } }),
}))
vi.mock('../src/features/video/useVideoRoom.js', () => ({
  useVideoRoom: () => roomState,
}))
vi.mock('../src/features/video/VideoStage.jsx', () => ({
  default: () => <div data-testid="video-stage" />,
}))
vi.mock('../src/features/video/VideoRoomSidebar.jsx', () => ({
  default: () => <aside data-testid="video-room-controls" />,
}))

import VideoRoomPage from '../src/pages/VideoRoomPage.jsx'

describe('video room community layout', () => {
  it('places online members and chat below the video before secondary controls', () => {
    render(
      <MemoryRouter initialEntries={['/rooms/watch/9']}>
        <Routes>
          <Route path="/rooms/watch/:id" element={<VideoRoomPage />} />
        </Routes>
      </MemoryRouter>,
    )

    const video = screen.getByTestId('video-stage')
    const community = screen.getByTestId('video-room-community')
    const controls = screen.getByTestId('video-room-controls')

    expect(video.compareDocumentPosition(community) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(community.compareDocumentPosition(controls) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByRole('heading', { name: '在线成员' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '聊天' })).toBeInTheDocument()
  })

  it('keeps room actions in an aligned body toolbar instead of a sticky header', () => {
    render(
      <MemoryRouter initialEntries={['/rooms/watch/9']}>
        <Routes>
          <Route path="/rooms/watch/:id" element={<VideoRoomPage />} />
        </Routes>
      </MemoryRouter>,
    )

    const toolbar = screen.getByRole('toolbar', { name: '观影房工具栏' })
    const video = screen.getByTestId('video-stage')

    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(toolbar).toContainElement(screen.getByRole('button', { name: '退出房间' }))
    expect(toolbar).toContainElement(screen.getByRole('button', { name: '复制分享链接' }))
    expect(toolbar).toContainElement(screen.getByRole('button', { name: '重新同步' }))
    expect(toolbar).toContainElement(screen.getByText('已与服务器同步'))
    expect(toolbar.compareDocumentPosition(video) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(toolbar).toHaveClass('max-w-[1600px]')
  })
})
