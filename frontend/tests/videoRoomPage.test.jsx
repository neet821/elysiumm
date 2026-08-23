import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'


const mocks = vi.hoisted(() => {
  const handlers = new Map()
  const socket = {
    disconnect: vi.fn(),
    emit: vi.fn(),
    on: vi.fn((eventName, handler) => handlers.set(eventName, handler)),
    off: vi.fn(),
  }
  const adapter = {
    destroy: vi.fn(),
    pause: vi.fn(),
    play: vi.fn(() => Promise.resolve()),
    seek: vi.fn(),
    setPlaybackRate: vi.fn(),
    setVolume: vi.fn(),
    snapshot: vi.fn(() => ({
      currentTime: 12,
      duration: 120,
      isPlaying: false,
      playbackRate: 1,
      track: { id: 'video:7' },
    })),
  }
  return {
    adapter,
    api: { delete: vi.fn(), get: vi.fn(), post: vi.fn(), put: vi.fn() },
    applySnapshot: vi.fn(async () => ({ applied: true, correction: 'none' })),
    createAdapter: vi.fn(() => adapter),
    handlers,
    io: vi.fn(() => socket),
    socket,
    user: { id: 1, role: 'user', username: 'host' },
    videoError: false,
  }
})

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ loading: false, user: mocks.user }),
}))
vi.mock('../src/utils/request.js', () => ({ default: mocks.api }))
vi.mock('socket.io-client', () => ({ io: mocks.io }))
vi.mock('../src/features/video/VideoPlayerAdapter.js', async (importOriginal) => ({
  ...(await importOriginal()),
  applyVideoSnapshot: mocks.applySnapshot,
  createVideoPlayerAdapter: mocks.createAdapter,
}))

import SyncRoomPlayer from '../src/pages/SyncRoomPlayer.jsx'
import { fingerprintLocalVideo } from '../src/features/video/localVideo.js'

const originalRequestFullscreen = window.HTMLElement.prototype.requestFullscreen

const snapshot = (overrides = {}) => ({
  media_id: 7,
  media_kind: 'video',
  playback_rate: 1,
  position: 12,
  room_id: 9,
  server_now_ms: 10_000,
  started_at_server_ms: 10_000,
  state: 'paused',
  version: 5,
  ...overrides,
})

const playlist = [
  {
    availability: 'available',
    duration_seconds: 120,
    id: 7,
    playback_url: '/api/video/items/7/stream?access=signed',
    position: 0,
    resolution: { height: 1080, width: 1920 },
    source_type: 'upload',
    subtitles: [{ id: 11, label: '中文', language: 'zh-CN', src: '/subtitles/11?access=signed' }],
    title: 'Shared film',
  },
  {
    availability: 'available',
    id: 8,
    playback_url: 'https://media.example/next.mp4',
    position: 1,
    source_type: 'external',
    subtitles: [],
    title: 'Next film',
  },
]

const videoDetail = (overrides = {}) => ({
  room: {
    control_mode: 'host_only',
    host_user_id: 1,
    id: 9,
    lifecycle_status: 'active',
    room_code: 'VIDEO9',
    room_name: 'Video room',
  },
  session: {
    current_item_id: 7,
    playlist,
    room_id: 9,
    selected_subtitle_id: 11,
  },
  snapshot: snapshot(),
  ...overrides,
})

beforeAll(() => {
  Object.defineProperty(window.HTMLMediaElement.prototype, 'load', {
    configurable: true,
    value: vi.fn(),
  })
  Object.defineProperty(window.HTMLMediaElement.prototype, 'pause', {
    configurable: true,
    value: vi.fn(),
  })
})

beforeEach(() => {
  mocks.user = { id: 1, role: 'user', username: 'host' }
  mocks.videoError = false
  mocks.handlers.clear()
  for (const value of Object.values(mocks.api)) value.mockReset().mockResolvedValue({ data: {} })
  for (const value of Object.values(mocks.adapter)) {
    if (typeof value?.mockClear === 'function') value.mockClear()
  }
  mocks.adapter.snapshot.mockReturnValue({
    currentTime: 12,
    duration: 120,
    isPlaying: false,
    playbackRate: 1,
    track: { id: 'video:7' },
  })
  mocks.applySnapshot.mockReset().mockResolvedValue({ applied: true, correction: 'none' })
  mocks.createAdapter.mockClear()
  mocks.socket.disconnect.mockClear()
  mocks.socket.emit.mockClear()
  mocks.socket.on.mockClear()
  mocks.socket.off.mockClear()
  mocks.io.mockClear()
  mocks.api.get.mockImplementation((url) => {
    if (url.endsWith('/api/sync-rooms/9/messages')) return Promise.resolve({ data: [] })
    if (url.endsWith('/api/sync-rooms/9')) {
      return Promise.resolve({
        data: {
          control_mode: 'host_only',
          host_user_id: 1,
          id: 9,
          members: [
            { is_online: true, user_id: 1, username: 'host' },
            { is_online: true, user_id: 2, username: 'member' },
          ],
          mode: 'url',
          room_code: 'VIDEO9',
          room_name: 'Video room',
          type: 'video',
        },
      })
    }
    if (url.endsWith('/api/video/rooms/9')) {
      return mocks.videoError
        ? Promise.reject(new Error('offline'))
        : Promise.resolve({ data: videoDetail() })
    }
    return Promise.reject(new Error(`Unexpected request: ${url}`))
  })
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value: 'visible',
  })
  Object.defineProperty(document, 'fullscreenElement', {
    configurable: true,
    value: null,
  })
})

afterEach(() => {
  if (originalRequestFullscreen) {
    window.HTMLElement.prototype.requestFullscreen = originalRequestFullscreen
  } else {
    delete window.HTMLElement.prototype.requestFullscreen
  }
  vi.restoreAllMocks()
})

function renderRoom() {
  return render(
    <MemoryRouter initialEntries={['/tools/sync-room/9']} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <Routes>
        <Route path="/tools/sync-room/:id" element={<SyncRoomPlayer isDark={false} />} />
        <Route path="/tools" element={<p>Tools</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('video room page', () => {
  it('loads the dedicated video domain and renders no game board', async () => {
    renderRoom()

    expect(await screen.findByRole('heading', { name: 'Video room' })).toBeInTheDocument()
    expect(screen.getByText('已与服务器同步')).toHaveAttribute('role', 'status')
    expect(screen.getByRole('button', { name: /播放 Shared film/ })).toBeEnabled()
    expect(screen.getByRole('option', { name: '中文' })).toBeInTheDocument()
    expect(screen.getByText('1920 × 1080')).toBeInTheDocument()
    expect(screen.queryByText(/井字棋|游戏棋盘/)).not.toBeInTheDocument()
    expect(mocks.api.get).toHaveBeenCalledWith(expect.stringMatching(/\/api\/video\/rooms\/9$/))
    expect(screen.getByRole('main')).toHaveClass('pt-[4.5rem]')
    expect(document.querySelector('main > header')).toHaveClass('top-[4.25rem]')
  })

  it('keeps host video controls when the saved user id is a string', async () => {
    mocks.user = { id: '1', role: 'user', username: 'host' }
    renderRoom()

    expect(await screen.findByLabelText('视频网址')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('视频网址'), {
      target: { value: 'https://media.example/host.mp4' },
    })
    expect(screen.getByRole('button', { name: '替换当前视频' })).toBeEnabled()
  })

  it('hides source controls from members when the room is host-only', async () => {
    mocks.user = { id: 2, role: 'user', username: 'member' }
    renderRoom()

    expect(await screen.findByRole('heading', { name: 'Video room' })).toBeInTheDocument()
    expect(screen.queryByLabelText('视频网址')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '上传视频' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '本地同步' })).not.toBeInTheDocument()
  })

  it('shows source controls to members when the room allows all members to control media', async () => {
    mocks.user = { id: 2, role: 'user', username: 'member' }
    mocks.api.get.mockImplementation((url) => {
      if (url.endsWith('/api/sync-rooms/9/messages')) return Promise.resolve({ data: [] })
      if (url.endsWith('/api/sync-rooms/9')) return Promise.resolve({ data: {
        control_mode: 'all_members',
        host_user_id: 1,
        id: 9,
        members: [{ is_online: true, user_id: 1, username: 'host' }, { is_online: true, user_id: 2, username: 'member' }],
        mode: 'url',
        room_code: 'VIDEO9',
        room_name: 'Video room',
        type: 'video',
      } })
      if (url.endsWith('/api/video/rooms/9')) return Promise.resolve({ data: videoDetail({ room: {
        control_mode: 'all_members',
        host_user_id: 1,
        id: 9,
        lifecycle_status: 'active',
        room_code: 'VIDEO9',
        room_name: 'Video room',
      } }) })
      return Promise.reject(new Error(`Unexpected request: ${url}`))
    })
    renderRoom()

    expect(await screen.findByLabelText('视频网址')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '上传视频' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '本地同步' })).toBeInTheDocument()
  })

  it('renders one current-video panel instead of a playlist', async () => {
    renderRoom()

    expect(await screen.findByText('当前视频')).toBeInTheDocument()
    expect(screen.queryByText('Next film')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /上移|下移|播放下一项/ })).not.toBeInTheDocument()
  })

  it('keeps the room usable when the initial video state is temporarily unavailable', async () => {
    mocks.videoError = true
    renderRoom()

    expect(await screen.findByRole('heading', { name: 'Video room' })).toBeInTheDocument()
    expect(screen.getByText('同步暂时失败')).toHaveAttribute('role', 'status')
    expect(screen.getByText('房间状态暂时无法同步，实时连接恢复后会自动重试')).toHaveAttribute('role', 'status')
    expect(screen.getByRole('button', { name: '重新同步' })).toBeEnabled()
  })

  it('starts playback from the user gesture while syncing the server state', async () => {
    renderRoom()
    const play = await screen.findByRole('button', { name: /播放 Shared film/ })
    mocks.socket.emit.mockClear()

    fireEvent.click(play)

    expect(mocks.socket.emit).toHaveBeenCalledWith('playback_control', {
      action: 'play',
      playback_version: 5,
      room_id: 9,
      time: 12,
    })
    expect(mocks.adapter.play).toHaveBeenCalledTimes(1)

    act(() => mocks.handlers.get('room_snapshot')(snapshot({ state: 'playing', version: 6 })))
    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalledWith(
      mocks.adapter,
      expect.objectContaining({ state: 'playing', version: 6 }),
      expect.objectContaining({ id: 'video:7:file:subtitles:11:1' }),
      expect.anything(),
    ))
  })

  it('rejoins, refreshes its signed session, restores snapshots and handles conflicts', async () => {
    renderRoom()
    await screen.findByRole('heading', { name: 'Video room' })

    act(() => mocks.handlers.get('connect')())
    expect(mocks.socket.emit).toHaveBeenCalledWith('join_room', { room_id: 9 })
    mocks.socket.emit.mockClear()
    act(() => mocks.handlers.get('disconnect')())
    expect(screen.getByText('连接中断，正在恢复…')).toHaveAttribute('role', 'status')
    act(() => mocks.handlers.get('connect')())
    expect(mocks.socket.emit).toHaveBeenCalledWith('join_room', { room_id: 9 })

    const initialVideoCalls = mocks.api.get.mock.calls.filter(([url]) => url.endsWith('/api/video/rooms/9')).length
    await act(async () => mocks.handlers.get('video_session_updated')({ room_id: 9 }))
    await waitFor(() => expect(
      mocks.api.get.mock.calls.filter(([url]) => url.endsWith('/api/video/rooms/9')).length,
    ).toBeGreaterThan(initialVideoCalls))

    mocks.socket.emit.mockClear()
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
      window.dispatchEvent(new Event('pageshow'))
    })
    expect(mocks.socket.emit).toHaveBeenCalledWith('request_snapshot', { room_id: 9 })

    act(() => mocks.handlers.get('playback_conflict')({
      snapshot: snapshot({ position: 20, version: 7 }),
    }))
    expect(await screen.findByText('操作与房间新状态冲突，已重新同步')).toHaveAttribute('role', 'status')
  })

  it('sends presence heartbeats only while the room page is visible', async () => {
    renderRoom()
    await screen.findByRole('heading', { name: 'Video room' })
    vi.useFakeTimers()
    try {
      act(() => mocks.handlers.get('join_success')({
        members: [
          { is_online: true, user_id: 1, username: 'host' },
          { is_online: true, user_id: 2, username: 'member' },
        ],
        snapshot: snapshot(),
      }))
      mocks.socket.emit.mockClear()
      act(() => vi.advanceTimersByTime(10_000))
      expect(mocks.socket.emit).toHaveBeenCalledWith('presence_heartbeat', { room_id: 9 })

      mocks.socket.emit.mockClear()
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
      act(() => document.dispatchEvent(new Event('visibilitychange')))
      act(() => vi.advanceTimersByTime(20_000))
      expect(mocks.socket.emit).not.toHaveBeenCalledWith('presence_heartbeat', { room_id: 9 })

      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
      act(() => document.dispatchEvent(new Event('visibilitychange')))
      expect(mocks.socket.emit).toHaveBeenCalledWith('presence_heartbeat', { room_id: 9 })
    } finally {
      vi.useRealTimers()
    }
  })

  it('applies a matching host heartbeat as a fresh video clock anchor', async () => {
    renderRoom()
    await screen.findByRole('heading', { name: 'Video room' })
    mocks.applySnapshot.mockClear()

    act(() => mocks.handlers.get('time_heartbeat')({
      position: 33,
      room_id: 9,
      server_now_ms: 20_000,
      version: 5,
    }))

    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalledWith(
      mocks.adapter,
      expect.objectContaining({
        position: 33,
        server_now_ms: 20_000,
        started_at_server_ms: 20_000,
        version: 5,
      }),
      expect.anything(),
      expect.anything(),
    ))
  })

  it('reports buffering and ended once with trusted server identifiers', async () => {
    renderRoom()
    await screen.findByRole('heading', { name: 'Video room' })
    const video = screen.getByTestId('video-room-media')
    mocks.socket.emit.mockClear()

    fireEvent.waiting(video)
    fireEvent.canPlay(video)
    fireEvent.ended(video)

    expect(mocks.socket.emit).toHaveBeenCalledWith('video_buffer_status', {
      buffering: true,
      item_id: 7,
      room_id: 9,
    })
    expect(mocks.socket.emit).toHaveBeenCalledWith('video_buffer_status', {
      buffering: false,
      item_id: 7,
      room_id: 9,
    })
    expect(mocks.socket.emit).toHaveBeenCalledTimes(3)
    expect(mocks.socket.emit).toHaveBeenCalledWith('video_ended', {
      expected_version: 5,
      item_id: 7,
      room_id: 9,
    })

    fireEvent.error(video)
    expect(screen.getByText('当前视频无法播放，请检查来源或稍后重试')).toHaveAttribute('role', 'status')
  })

  it('rejects native mobile playback when the member cannot control the room', async () => {
    mocks.user = { id: 2, role: 'user', username: 'member' }
    renderRoom()
    const video = await screen.findByTestId('video-room-media')
    mocks.adapter.pause.mockClear()
    mocks.socket.emit.mockClear()

    fireEvent.play(video)

    expect(mocks.adapter.pause).toHaveBeenCalledTimes(1)
    expect(mocks.socket.emit).not.toHaveBeenCalledWith(
      'playback_control',
      expect.anything(),
    )
  })

  it('shows upload progress while the video request is pending', async () => {
    renderRoom()
    await screen.findByRole('heading', { name: 'Video room' })
    fireEvent.click(screen.getByRole('button', { name: '上传视频' }))
    const input = screen.getByLabelText('上传视频')
    const file = new File(['video'], 'movie.mp4', { type: 'video/mp4' })
    let resolveUpload
    let uploadConfig
    mocks.api.post.mockImplementationOnce((url, form, config) => {
      uploadConfig = config
      return new Promise((resolve) => { resolveUpload = resolve })
    })

    fireEvent.change(input, { target: { files: [file] } })
    await waitFor(() => expect(screen.getByLabelText('视频上传进度')).toBeInTheDocument())
    act(() => uploadConfig.onUploadProgress({ loaded: 50, total: 100 }))

    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByText('50 B / 100 B')).toBeInTheDocument()
    expect(input).toBeDisabled()

    await act(async () => { resolveUpload({ data: {} }) })
    await waitFor(() => expect(screen.queryByLabelText('视频上传进度')).not.toBeInTheDocument())
  })

  it('clears upload progress and shows the server error after upload failure', async () => {
    renderRoom()
    await screen.findByRole('heading', { name: 'Video room' })
    fireEvent.click(screen.getByRole('button', { name: '上传视频' }))
    const input = screen.getByLabelText('上传视频')
    mocks.api.post.mockImplementationOnce(() => Promise.reject({ response: { data: { detail: '视频太大' } } }))

    fireEvent.change(input, {
      target: { files: [new File(['video'], 'movie.mp4', { type: 'video/mp4' })] },
    })

    expect(await screen.findByText('视频太大')).toHaveAttribute('role', 'status')
    expect(screen.queryByLabelText('视频上传进度')).not.toBeInTheDocument()
  })

  it('re-announces a matching local video after the realtime room reconnects', async () => {
    const file = new File(['local'], 'movie.mp4', { type: 'video/mp4' })
    Object.defineProperty(file, 'slice', {
      configurable: true,
      value: vi.fn(() => ({ arrayBuffer: async () => Uint8Array.from([1, 2, 3]).buffer })),
    })
    const fingerprint = await fingerprintLocalVideo(file)
    const localItem = {
      ...playlist[0],
      file_size: file.size,
      id: 20,
      local_fingerprint: fingerprint,
      playback_url: null,
      source_type: 'legacy_local',
      title: 'movie.mp4',
    }
    const localDetail = videoDetail({
      session: { ...videoDetail().session, current_item_id: 20, playlist: [localItem] },
      snapshot: snapshot({ media_id: 20 }),
    })
    mocks.api.get.mockImplementation((url) => {
      if (url.endsWith('/api/sync-rooms/9/messages')) return Promise.resolve({ data: [] })
      if (url.endsWith('/api/sync-rooms/9')) return Promise.resolve({ data: {
        control_mode: 'host_only', host_user_id: 1, id: 9,
        members: [{ is_online: true, user_id: 1, username: 'host' }],
        mode: 'local', room_code: 'VIDEO9', room_name: 'Video room', type: 'video',
      } })
      if (url.endsWith('/api/video/rooms/9')) return Promise.resolve({ data: localDetail })
      return Promise.reject(new Error(`Unexpected request: ${url}`))
    })
    mocks.api.post.mockImplementation((url) => url.endsWith('/items/local')
      ? Promise.resolve({ data: { item: localItem } })
      : Promise.resolve({ data: {} }))
    renderRoom()
    await screen.findByRole('heading', { name: 'Video room' })
    fireEvent.click(screen.getByRole('button', { name: '本地同步' }))
    fireEvent.change(screen.getByLabelText('登记本地视频'), { target: { files: [file] } })
    await waitFor(() => expect(mocks.socket.emit).toHaveBeenCalledWith('video_local_ready', {
      fingerprint,
      item_id: 20,
      ready: true,
      room_id: 9,
    }))

    mocks.socket.emit.mockClear()
    act(() => mocks.handlers.get('join_success')({
      room: { control_mode: 'host_only', host_user_id: 1 },
      members: [{ is_online: true, user_id: 1, username: 'host' }],
      snapshot: snapshot({ media_id: 20 }),
      video_session: localDetail.session,
    }))

    expect(mocks.socket.emit).toHaveBeenCalledWith('video_local_ready', {
      fingerprint,
      item_id: 20,
      ready: true,
      room_id: 9,
    })
  })

  it('applies realtime online and offline member states without duplicating members', async () => {
    renderRoom()
    await screen.findByRole('heading', { name: 'Video room' })

    act(() => mocks.handlers.get('room_presence')({
      room_id: 9,
      members: [
        { is_online: false, user_id: 1, username: 'host' },
        { is_online: true, user_id: 2, username: 'member' },
      ],
    }))
    expect(screen.getByText('离线')).toBeInTheDocument()

    act(() => mocks.handlers.get('room_presence')({
      room_id: 9,
      members: [
        { is_online: true, user_id: 1, username: 'host' },
        { is_online: true, user_id: 2, username: 'member' },
      ],
    }))
    expect(screen.getAllByText('在线')).toHaveLength(2)
  })

  it('does not resubmit metadata that already matches the current video', async () => {
    renderRoom()
    await screen.findByRole('heading', { name: 'Video room' })
    const video = screen.getByTestId('video-room-media')
    Object.defineProperties(video, {
      duration: { configurable: true, value: 120 },
      videoHeight: { configurable: true, value: 1080 },
      videoWidth: { configurable: true, value: 1920 },
    })
    mocks.api.put.mockClear()

    fireEvent.loadedMetadata(video)

    expect(mocks.api.put).not.toHaveBeenCalled()
  })

  it('keeps fullscreen and volume local while rate remains shared', async () => {
    const requestFullscreen = vi.fn(() => Promise.resolve())
    window.HTMLElement.prototype.requestFullscreen = requestFullscreen
    renderRoom()
    await screen.findByRole('heading', { name: 'Video room' })
    mocks.socket.emit.mockClear()

    fireEvent.change(screen.getByLabelText('本机音量'), { target: { value: '0.4' } })
    fireEvent.change(screen.getByLabelText('共享播放速度'), { target: { value: '1.25' } })
    fireEvent.click(screen.getByRole('button', { name: '全屏播放' }))

    expect(mocks.adapter.setVolume).toHaveBeenCalledWith(0.4)
    expect(requestFullscreen).toHaveBeenCalledTimes(1)
    expect(mocks.socket.emit).toHaveBeenCalledTimes(1)
    expect(mocks.socket.emit).toHaveBeenCalledWith('playback_control', {
      action: 'rate',
      playback_version: 5,
      rate: 1.25,
      room_id: 9,
    })
  })

  it('manages URL items and cleans the socket and adapter on unmount', async () => {
    const view = renderRoom()
    await screen.findByRole('heading', { name: 'Video room' })
    expect(screen.getByText('支持 MP4、WebM、MOV、Ogg 和 HLS 文件直链，不支持普通视频网页。')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('视频网址'), {
      target: { value: 'https://media.example/new.mp4' },
    })
    fireEvent.click(screen.getByRole('button', { name: '替换当前视频' }))

    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/video\/rooms\/9\/items\/url$/),
      {
        source_url: 'https://media.example/new.mp4',
        title: 'https://media.example/new.mp4',
      },
    ))
    view.unmount()
    expect(mocks.socket.disconnect).toHaveBeenCalledTimes(1)
    expect(mocks.adapter.destroy).toHaveBeenCalledTimes(1)
  })
})
