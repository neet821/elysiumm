import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { requestGet, requestPost, requestPatch, requestDelete, requestPut } = vi.hoisted(() => ({
  requestGet: vi.fn(),
  requestPost: vi.fn(),
  requestPatch: vi.fn(),
  requestDelete: vi.fn(),
  requestPut: vi.fn(),
}))

vi.mock('../src/utils/request.js', () => ({
  default: {
    get: requestGet,
    post: requestPost,
    patch: requestPatch,
    delete: requestDelete,
    put: requestPut,
  },
}))

import MusicPlaylistManager from '../src/features/music/MusicPlaylistManager.jsx'

const playlist = {
  id: 7,
  name: '夜路',
  source: { provider: 'netease', playlist_id: '163', url: 'https://music.163.com/playlist?id=163' },
  tracks: [
    { id: 31, provider: 'netease', provider_track_id: '101', title: '曲目一', artist: '歌手甲', duration_seconds: 180, availability: 'playable', position: 0 },
    { id: 32, provider: 'netease', provider_track_id: '102', title: '曲目二', artist: '歌手乙', duration_seconds: 200, availability: 'unavailable', position: 1 },
  ],
}

function setInitialResponses(playlists = [playlist]) {
  requestGet.mockImplementation(async (url) => {
    if (url.endsWith('/api/music/playlists')) return { data: { playlists } }
    if (url.endsWith('/api/sync-rooms')) return { data: [{ id: 9, mode: 'music', room_name: '蓝色听歌房' }] }
    throw new Error(`unexpected GET ${url}`)
  })
}

describe('personal music playlists', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  beforeEach(() => {
    requestGet.mockReset()
    requestPost.mockReset()
    requestPatch.mockReset()
    requestDelete.mockReset()
    requestPut.mockReset()
    setInitialResponses()
  })

  it('creates and renames an owner-private playlist through the playlist API', async () => {
    const user = userEvent.setup()
    requestPost.mockResolvedValue({ data: { ...playlist, id: 8, name: '通勤' } })
    requestPatch.mockResolvedValue({ data: { ...playlist, id: 8, name: '夜班' } })
    requestDelete.mockResolvedValue({ data: { deleted: true } })
    vi.stubGlobal('confirm', vi.fn(() => true))
    render(<MusicPlaylistManager />)

    await user.type(await screen.findByLabelText('创建歌单'), '通勤')
    await user.click(screen.getByRole('button', { name: '创建歌单' }))
    await waitFor(() => expect(requestPost).toHaveBeenCalledWith(expect.stringMatching(/\/api\/music\/playlists$/), { name: '通勤' }))
    expect(await screen.findByRole('button', { name: /通勤/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '重命名歌单' }))
    const renameField = screen.getByLabelText('歌单新名称')
    await user.clear(renameField)
    await user.type(renameField, '夜班')
    await user.click(screen.getByRole('button', { name: '保存名称' }))
    await waitFor(() => expect(requestPatch).toHaveBeenCalledWith(expect.stringMatching(/\/api\/music\/playlists\/8$/), { name: '夜班' }))
    await user.click(screen.getByRole('button', { name: '删除歌单' }))
    await waitFor(() => expect(requestDelete).toHaveBeenCalledWith(expect.stringMatching(/\/api\/music\/playlists\/8$/)))
    vi.unstubAllGlobals()
  })

  it('previews a public NetEase playlist and imports only after confirmation', async () => {
    const user = userEvent.setup()
    requestGet.mockImplementation(async (url, options) => {
      if (url.endsWith('/api/music/playlists')) return { data: { playlists: [] } }
      if (url.endsWith('/api/sync-rooms')) return { data: [] }
      if (url.endsWith('/api/music/playlists/import/preview')) {
        return { data: { provider: 'netease', source_playlist_id: '163', name: '来源歌单', track_count: 2, unavailable_count: 1, missing_count: 1, tracks: [
          { provider: 'netease', provider_track_id: '201', title: '可用曲目', artist: '甲', availability: 'playable', missing: false },
          { provider: 'netease', provider_track_id: null, title: '未能读取的歌曲 #2', artist: '未知音乐人', availability: 'unavailable', missing: true },
        ] } }
      }
      throw new Error(`unexpected GET ${url} ${JSON.stringify(options)}`)
    })
    requestPost.mockResolvedValue({ data: { created: true, playlist: { ...playlist, id: 15, name: '来源歌单' } } })
    render(<MusicPlaylistManager />)

    await user.type(await screen.findByLabelText('导入网易云公开歌单'), '163')
    await user.click(screen.getByRole('button', { name: '预览歌单' }))
    expect(await screen.findByText(/未能读取的歌曲 #2/)).toBeInTheDocument()
    expect(screen.getByText(/1 首缺失，1 首不可用/)).toBeInTheDocument()
    expect(requestPost).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: '确认导入副本' }))
    await waitFor(() => expect(requestPost).toHaveBeenCalledWith(expect.stringMatching(/\/api\/music\/playlists\/import$/), { reference: '163' }))
  })

  it('adds searched songs, preserves unavailable items, reorders and removes tracks', async () => {
    const user = userEvent.setup()
    requestGet.mockImplementation(async (url, options) => {
      if (url.endsWith('/api/music/playlists')) return { data: { playlists: [playlist] } }
      if (url.endsWith('/api/sync-rooms')) return { data: [] }
      if (url.endsWith('/api/music/search')) return { data: { items: [{
        id: 88, title: '新曲', artist: '歌手丙', album: '專輯', duration_seconds: 210,
        providers: [{ provider: 'qq', provider_track_id: 'qq-88' }],
      }] } }
      throw new Error(`unexpected GET ${url} ${JSON.stringify(options)}`)
    })
    requestPost.mockResolvedValue({ data: playlist })
    requestPut.mockResolvedValue({ data: playlist })
    requestDelete.mockResolvedValue({ data: playlist })
    render(<MusicPlaylistManager />)

    expect(await screen.findByText('不可用')).toBeInTheDocument()
    await user.type(screen.getByLabelText('搜索歌曲加入歌单'), '新曲')
    await user.click(screen.getByRole('button', { name: '搜索曲库' }))
    await user.click(await screen.findByRole('button', { name: '将《新曲》加入歌单' }))
    await waitFor(() => expect(requestPost).toHaveBeenCalledWith(expect.stringMatching(/\/api\/music\/playlists\/7\/tracks$/), expect.objectContaining({
      provider: 'qq', provider_track_id: 'qq-88', title: '新曲', artist: '歌手丙', canonical_track_id: 88,
    })))

    await user.click(screen.getByRole('button', { name: '上移《曲目二》' }))
    expect(requestPut).toHaveBeenCalledWith(expect.stringMatching(/\/api\/music\/playlists\/7\/tracks\/order$/), { item_ids: [32, 31] })
    await user.click(screen.getByRole('button', { name: '从歌单移除《曲目一》' }))
    expect(requestDelete).toHaveBeenCalledWith(expect.stringMatching(/\/api\/music\/playlists\/7\/tracks\/31$/))
  })

  it('appends selected playlist tracks to an existing music-room queue without replacing it', async () => {
    const user = userEvent.setup()
    requestPost.mockResolvedValue({ data: { added_count: 1, skipped: [{ playlist_item_id: 32, reason: 'not_playable' }] } })
    setInitialResponses()
    render(<MusicPlaylistManager />)

    await user.selectOptions(await screen.findByLabelText('追加目标听歌房'), '9')
    await user.click(screen.getByRole('button', { name: '追加到听歌房队列' }))
    await waitFor(() => expect(requestPost).toHaveBeenCalledWith(expect.stringMatching(/\/api\/music\/rooms\/9\/playlists\/7\/queue$/), { item_ids: [31, 32] }))
    expect(await screen.findByText('追加了 1 首，1 首被跳过或不可用。')).toBeInTheDocument()
  })

  it('appends playlists larger than the API batch limit in ordered batches and aggregates outcomes', async () => {
    const user = userEvent.setup()
    const tracks = Array.from({ length: 205 }, (_, index) => ({
      id: index + 1,
      provider: 'netease',
      provider_track_id: String(index + 1),
      title: `曲目${index + 1}`,
      artist: '歌手',
      duration_seconds: 180,
      availability: 'playable',
      position: index,
    }))
    setInitialResponses([{ ...playlist, tracks }])
    requestPost
      .mockResolvedValueOnce({ data: { added_count: 100, skipped: [] } })
      .mockResolvedValueOnce({ data: { added_count: 99, skipped: [{ reason: 'not_playable' }] } })
      .mockResolvedValueOnce({ data: { added_count: 4, skipped: [{ reason: 'already_in_queue' }] } })
    render(<MusicPlaylistManager />)

    await user.selectOptions(await screen.findByLabelText('追加目标听歌房'), '9')
    await user.click(screen.getByRole('button', { name: '追加到听歌房队列' }))

    await waitFor(() => expect(requestPost).toHaveBeenCalledTimes(3))
    const queueRequests = requestPost.mock.calls.filter(([url]) => /\/api\/music\/rooms\/9\/playlists\/7\/queue$/.test(url))
    expect(queueRequests.map(([, payload]) => payload.item_ids)).toEqual([
      Array.from({ length: 100 }, (_, index) => index + 1),
      Array.from({ length: 100 }, (_, index) => index + 101),
      [201, 202, 203, 204, 205],
    ])
    expect(await screen.findByText('追加了 203 首，2 首被跳过或不可用。')).toBeInTheDocument()
  })

  it('keeps private playlists visible when the separate room-list request is unavailable', async () => {
    requestGet.mockImplementation(async (url) => {
      if (url.endsWith('/api/music/playlists')) return { data: { playlists: [playlist] } }
      if (url.endsWith('/api/sync-rooms')) throw new Error('room service unavailable')
      throw new Error(`unexpected GET ${url}`)
    })
    render(<MusicPlaylistManager />)

    expect(await screen.findByRole('button', { name: /夜路/ })).toBeInTheDocument()
    expect(await screen.findByText(/听歌房列表暂时无法载入/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('reports confirmed partial progress when a later queue batch fails', async () => {
    const user = userEvent.setup()
    const tracks = Array.from({ length: 101 }, (_, index) => ({
      id: index + 1,
      provider: 'netease',
      provider_track_id: String(index + 1),
      title: `曲目${index + 1}`,
      artist: '歌手',
      duration_seconds: 180,
      availability: 'playable',
      position: index,
    }))
    setInitialResponses([{ ...playlist, tracks }])
    requestPost
      .mockResolvedValueOnce({ data: { added_count: 100, skipped: [] } })
      .mockRejectedValueOnce(new Error('network failure'))
    render(<MusicPlaylistManager />)

    await user.selectOptions(await screen.findByLabelText('追加目标听歌房'), '9')
    await user.click(screen.getByRole('button', { name: '追加到听歌房队列' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('前 1 批已确认追加 100 首')
    expect(screen.getByRole('alert')).toHaveTextContent('后续批次结果未知')
    const queueRequests = requestPost.mock.calls.filter(([url]) => /\/api\/music\/rooms\/9\/playlists\/7\/queue$/.test(url))
    expect(queueRequests).toHaveLength(2)
    expect(queueRequests[0][1].item_ids).toHaveLength(100)
    expect(queueRequests[1][1].item_ids).toEqual([101])
  })
})
