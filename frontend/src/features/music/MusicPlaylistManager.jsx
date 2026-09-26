import { useEffect, useMemo, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'

const availabilityLabel = {
  playable: '可播放',
  preview: '试听',
  unavailable: '不可用',
}

function playlistFrom(response) {
  return response?.data?.playlist || response?.data
}

export default function MusicPlaylistManager() {
  const [playlists, setPlaylists] = useState([])
  const [selectedPlaylistId, setSelectedPlaylistId] = useState(null)
  const [rooms, setRooms] = useState([])
  const [selectedRoomId, setSelectedRoomId] = useState('')
  const [newName, setNewName] = useState('')
  const [renameValue, setRenameValue] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [sourceReference, setSourceReference] = useState('')
  const [importPreview, setImportPreview] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const selectedPlaylist = useMemo(
    () => playlists.find((playlist) => playlist.id === selectedPlaylistId) || playlists[0] || null,
    [playlists, selectedPlaylistId],
  )

  useEffect(() => {
    let active = true
    void (async () => {
      const [playlistResult, roomResult] = await Promise.allSettled([
        apiClient.get(API_ENDPOINTS.MUSIC_PLAYLISTS),
        apiClient.get(API_ENDPOINTS.SYNC_ROOMS),
      ])
      if (!active) return
      if (playlistResult.status === 'rejected') {
        setError(playlistResult.reason.response?.data?.detail || '歌单暂时无法载入。')
        return
      }
      const items = playlistResult.value.data?.playlists || []
      setPlaylists(items)
      setSelectedPlaylistId(items[0]?.id ?? null)
      if (roomResult.status === 'fulfilled') {
        setRooms((roomResult.value.data || []).filter((room) => room.mode === 'music'))
      } else {
        setNotice('听歌房列表暂时无法载入；歌单仍可管理，稍后再试追加队列。')
      }
    })()
    return () => { active = false }
  }, [])

  const applyPlaylist = (playlist) => {
    if (!playlist || typeof playlist.id !== 'number') return
    setPlaylists((items) => {
      const exists = items.some((item) => item.id === playlist.id)
      return exists
        ? items.map((item) => item.id === playlist.id ? playlist : item)
        : [playlist, ...items]
    })
    setSelectedPlaylistId(playlist.id)
  }

  const runAction = async (action, successMessage = '') => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const response = await action()
      if (successMessage) setNotice(successMessage(response))
      return response
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '操作失败，请稍后重试。')
      return null
    } finally {
      setBusy(false)
    }
  }

  const createPlaylist = async (event) => {
    event.preventDefault()
    const name = newName.trim()
    if (!name) return
    const response = await runAction(() => apiClient.post(API_ENDPOINTS.MUSIC_PLAYLISTS, { name }))
    const created = playlistFrom(response)
    if (created) applyPlaylist(created)
    setNewName('')
  }

  const saveRename = async (event) => {
    event.preventDefault()
    if (!selectedPlaylist || !renameValue.trim()) return
    const response = await runAction(() => apiClient.patch(
      API_ENDPOINTS.MUSIC_PLAYLIST(selectedPlaylist.id),
      { name: renameValue.trim() },
    ))
    const renamed = playlistFrom(response)
    if (renamed) applyPlaylist(renamed)
    setRenaming(false)
  }

  const deletePlaylist = async () => {
    if (!selectedPlaylist || !window.confirm(`删除歌单“${selectedPlaylist.name}”？`)) return
    const deleted = await runAction(() => apiClient.delete(API_ENDPOINTS.MUSIC_PLAYLIST(selectedPlaylist.id)))
    if (deleted) {
      const remaining = playlists.filter((playlist) => playlist.id !== selectedPlaylist.id)
      setPlaylists(remaining)
      setSelectedPlaylistId(remaining[0]?.id ?? null)
    }
  }

  const previewImport = async (event) => {
    event.preventDefault()
    const reference = sourceReference.trim()
    if (!reference) return
    const response = await runAction(() => apiClient.get(API_ENDPOINTS.MUSIC_PLAYLIST_IMPORT_PREVIEW, {
      params: { reference },
    }))
    setImportPreview(response?.data || null)
  }

  const confirmImport = async () => {
    const response = await runAction(() => apiClient.post(API_ENDPOINTS.MUSIC_PLAYLIST_IMPORT, {
      reference: sourceReference.trim(),
    }), (value) => value?.data?.created ? '已导入为独立副本。' : '该来源歌单此前已导入，已打开现有副本。')
    const imported = playlistFrom(response)
    if (imported) applyPlaylist(imported)
    if (response) {
      setImportPreview(null)
      setSourceReference('')
    }
  }

  const searchTracks = async (event) => {
    event.preventDefault()
    if (!searchQuery.trim() || !selectedPlaylist) return
    const response = await runAction(() => apiClient.get(API_ENDPOINTS.MUSIC_SEARCH, {
      params: { limit: 12, provider: 'netease', q: searchQuery.trim() },
    }))
    setSearchResults(response?.data?.items || [])
  }

  const addTrack = async (result) => {
    const provider = result.providers?.find((item) => item.provider === 'netease') || result.providers?.[0]
    if (!selectedPlaylist || !provider) return
    const response = await runAction(() => apiClient.post(
      API_ENDPOINTS.MUSIC_PLAYLIST_TRACKS(selectedPlaylist.id),
      {
        provider: provider.provider,
        provider_track_id: provider.provider_track_id,
        title: result.title,
        artist: result.artist,
        album: result.album,
        artwork_url: result.artwork_url,
        duration_seconds: result.duration_seconds,
        canonical_track_id: result.id,
      },
    ))
    const updated = playlistFrom(response)
    if (updated) applyPlaylist(updated)
    setSearchResults((items) => items.filter((item) => item.id !== result.id))
  }

  const removeTrack = async (item) => {
    if (!selectedPlaylist) return
    const response = await runAction(() => apiClient.delete(
      API_ENDPOINTS.MUSIC_PLAYLIST_TRACK(selectedPlaylist.id, item.id),
    ))
    const updated = playlistFrom(response)
    if (updated) applyPlaylist(updated)
  }

  const moveTrack = async (index, offset) => {
    if (!selectedPlaylist) return
    const ids = selectedPlaylist.tracks.map((item) => item.id)
    const target = index + offset
    if (target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    const response = await runAction(() => apiClient.put(
      API_ENDPOINTS.MUSIC_PLAYLIST_ORDER(selectedPlaylist.id),
      { item_ids: ids },
    ))
    const updated = playlistFrom(response)
    if (updated) applyPlaylist(updated)
  }

  const appendToRoom = async () => {
    if (!selectedPlaylist || !selectedRoomId) return
    const itemIds = (selectedPlaylist.tracks || []).map((item) => item.id)
    const response = await runAction(
      async () => {
        const results = []
        const endpoint = API_ENDPOINTS.MUSIC_PLAYLIST_QUEUE(selectedRoomId, selectedPlaylist.id)
        for (let offset = 0; offset < itemIds.length; offset += 100) {
          try {
            results.push(await apiClient.post(endpoint, { item_ids: itemIds.slice(offset, offset + 100) }))
          } catch (requestError) {
            if (results.length > 0) {
              const added = results.reduce((total, result) => total + (result.data?.added_count || 0), 0)
              throw {
                response: {
                  data: {
                    detail: `前 ${results.length} 批已确认追加 ${added} 首；后续批次结果未知，请先检查听歌房队列再重试。`,
                  },
                },
              }
            }
            throw requestError
          }
        }
        return {
          data: {
            added_count: results.reduce((total, result) => total + (result.data?.added_count || 0), 0),
            skipped: results.flatMap((result) => result.data?.skipped || []),
          },
        }
      },
      (value) => {
        const result = value?.data || {}
        const skipped = result.skipped?.length || 0
        return `追加了 ${result.added_count || 0} 首，${skipped} 首被跳过或不可用。`
      },
    )
    if (response) setNotice((message) => message || '队列已更新。')
  }

  return (
    <section aria-labelledby="music-playlists-title" className="mx-auto my-8 w-full max-w-6xl px-4 sm:px-6">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm text-[var(--text-grey)]">个人收藏 · 私有副本</p>
          <h1 className="text-2xl font-semibold text-[var(--text-dark)]" id="music-playlists-title">我的歌单</h1>
        </div>
        <p className="text-sm text-[var(--text-grey)]">导入的网易云歌单不会自动同步或回写来源平台。</p>
      </header>

      {error && <p className="mb-4 rounded-lg border border-red-300 bg-red-50 p-3 text-red-800" role="alert">{error}</p>}
      {notice && <p className="mb-4 rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-emerald-900" role="status">{notice}</p>}

      <div className="grid gap-5 lg:grid-cols-[minmax(15rem,0.8fr)_minmax(0,1.6fr)]">
        <aside className="space-y-5">
          <form className="rounded-xl border border-[var(--border-color)] bg-[var(--surface-color)] p-4" onSubmit={createPlaylist}>
            <label className="mb-2 block text-sm font-medium" htmlFor="music-playlist-new-name">创建歌单</label>
            <div className="flex gap-2">
              <input className="min-w-0 flex-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-color)] px-3 py-2" id="music-playlist-new-name" maxLength={120} onChange={(event) => setNewName(event.target.value)} value={newName} />
              <button className="rounded-lg bg-[#2A5C8D] px-3 py-2 text-white disabled:opacity-50" disabled={busy || !newName.trim()} type="submit">创建歌单</button>
            </div>
          </form>

          <form className="rounded-xl border border-[var(--border-color)] bg-[var(--surface-color)] p-4" onSubmit={previewImport}>
            <label className="mb-2 block text-sm font-medium" htmlFor="music-playlist-import-reference">导入网易云公开歌单</label>
            <input className="mb-2 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-color)] px-3 py-2" id="music-playlist-import-reference" onChange={(event) => { setSourceReference(event.target.value); setImportPreview(null) }} placeholder="粘贴歌单链接或 ID" value={sourceReference} />
            <button className="rounded-lg border border-[var(--border-color)] px-3 py-2 disabled:opacity-50" disabled={busy || !sourceReference.trim()} type="submit">预览歌单</button>
            {importPreview && (
              <div className="mt-4 rounded-lg bg-[var(--bg-color)] p-3" aria-label="歌单导入预览">
                <h2 className="font-semibold">{importPreview.name}</h2>
                <p className="text-sm text-[var(--text-grey)]">{importPreview.track_count} 首 · {importPreview.missing_count} 首缺失，{importPreview.unavailable_count} 首不可用</p>
                <ul className="mt-2 max-h-48 space-y-1 overflow-auto text-sm">
                  {(importPreview.tracks || []).map((track, index) => (
                    <li key={`${track.provider_track_id || 'missing'}-${index}`}>
                      {track.title} · {track.artist} · {availabilityLabel[track.availability] || '不可用'}
                      {track.missing ? '（来源条目缺失）' : ''}
                    </li>
                  ))}
                </ul>
                <button className="mt-3 rounded-lg bg-[#2A5C8D] px-3 py-2 text-white disabled:opacity-50" disabled={busy} onClick={confirmImport} type="button">确认导入副本</button>
              </div>
            )}
          </form>

          <nav aria-label="个人歌单" className="rounded-xl border border-[var(--border-color)] bg-[var(--surface-color)] p-3">
            <h2 className="px-2 pb-2 font-semibold">歌单</h2>
            {playlists.length === 0
              ? <p className="px-2 py-3 text-sm text-[var(--text-grey)]">还没有歌单，可以创建或导入一个。</p>
              : <ul className="space-y-1">{playlists.map((playlist) => (
                <li key={playlist.id}>
                  <button aria-current={selectedPlaylist?.id === playlist.id ? 'page' : undefined} className="w-full rounded-lg px-3 py-2 text-left hover:bg-[var(--bg-color)] aria-[current=page]:bg-[var(--bg-color)]" onClick={() => { setSelectedPlaylistId(playlist.id); setRenaming(false) }} type="button">
                    <span className="block font-medium">{playlist.name}</span>
                    <span className="block text-xs text-[var(--text-grey)]">{playlist.tracks?.length || 0} 首{playlist.source ? ' · 网易云导入副本' : ''}</span>
                  </button>
                </li>
              ))}</ul>}
          </nav>
        </aside>

        <div className="min-w-0 rounded-xl border border-[var(--border-color)] bg-[var(--surface-color)] p-4 sm:p-5">
          {!selectedPlaylist ? <p className="py-8 text-center text-[var(--text-grey)]">选择或创建歌单后即可管理歌曲。</p> : (
            <>
              <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-xl font-semibold">{selectedPlaylist.name}</h2>
                  <p className="text-sm text-[var(--text-grey)]">{selectedPlaylist.tracks?.length || 0} 首歌曲{selectedPlaylist.source ? ' · 导入副本' : ''}</p>
                </div>
                <div className="flex gap-2">
                  <button className="rounded-lg border border-[var(--border-color)] px-3 py-2" onClick={() => { setRenameValue(selectedPlaylist.name); setRenaming((value) => !value) }} type="button">重命名歌单</button>
                  <button className="rounded-lg border border-red-300 px-3 py-2 text-red-700" onClick={deletePlaylist} type="button">删除歌单</button>
                </div>
              </header>

              {renaming && <form className="mb-4 flex gap-2" onSubmit={saveRename}>
                <input aria-label="歌单新名称" className="min-w-0 flex-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-color)] px-3 py-2" maxLength={120} onChange={(event) => setRenameValue(event.target.value)} value={renameValue} />
                <button className="rounded-lg bg-[#2A5C8D] px-3 py-2 text-white" disabled={busy || !renameValue.trim()} type="submit">保存名称</button>
              </form>}

              <form className="mb-4 flex gap-2" onSubmit={searchTracks}>
                <input aria-label="搜索歌曲加入歌单" className="min-w-0 flex-1 rounded-lg border border-[var(--border-color)] bg-[var(--bg-color)] px-3 py-2" onChange={(event) => setSearchQuery(event.target.value)} placeholder="搜索网易云歌曲" value={searchQuery} />
                <button className="rounded-lg border border-[var(--border-color)] px-3 py-2" disabled={busy || !searchQuery.trim()} type="submit">搜索曲库</button>
              </form>
              {searchResults.length > 0 && <ul aria-label="搜索结果" className="mb-4 divide-y divide-[var(--border-color)] rounded-lg border border-[var(--border-color)] px-3">
                {searchResults.map((result) => <li className="flex items-center justify-between gap-3 py-2" key={result.id}>
                  <span><strong>{result.title}</strong><small className="block text-[var(--text-grey)]">{result.artist}{result.album ? ` · ${result.album}` : ''}</small></span>
                  <button className="rounded-lg border border-[var(--border-color)] px-3 py-1" onClick={() => addTrack(result)} type="button">将《{result.title}》加入歌单</button>
                </li>)}
              </ul>}

              <ul aria-label="歌单歌曲" className="divide-y divide-[var(--border-color)] rounded-lg border border-[var(--border-color)] px-3">
                {(selectedPlaylist.tracks || []).map((track, index, tracks) => <li className="flex flex-wrap items-center justify-between gap-3 py-3" key={track.id}>
                  <div className="min-w-0">
                    <p className="truncate font-medium">{track.title}</p>
                    <p className="text-sm text-[var(--text-grey)]">{track.artist}{track.album ? ` · ${track.album}` : ''}</p>
                    <span className="text-xs text-[var(--text-grey)]">{track.missing || !track.provider_track_id ? '来源条目缺失' : availabilityLabel[track.availability] || '不可用'}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <button aria-label={`上移《${track.title}》`} className="rounded border border-[var(--border-color)] px-2 py-1 disabled:opacity-40" disabled={busy || index === 0} onClick={() => moveTrack(index, -1)} type="button">↑</button>
                    <button aria-label={`下移《${track.title}》`} className="rounded border border-[var(--border-color)] px-2 py-1 disabled:opacity-40" disabled={busy || index === tracks.length - 1} onClick={() => moveTrack(index, 1)} type="button">↓</button>
                    <button aria-label={`从歌单移除《${track.title}》`} className="rounded border border-red-300 px-2 py-1 text-red-700" disabled={busy} onClick={() => removeTrack(track)} type="button">移除</button>
                  </div>
                </li>)}
                {(selectedPlaylist.tracks || []).length === 0 && <li className="py-5 text-center text-sm text-[var(--text-grey)]">歌单还是空的。</li>}
              </ul>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <label className="sr-only" htmlFor="music-playlist-target-room">追加目标听歌房</label>
                <select className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-color)] px-3 py-2" id="music-playlist-target-room" onChange={(event) => setSelectedRoomId(event.target.value)} value={selectedRoomId}>
                  <option value="">选择听歌房</option>
                  {rooms.map((room) => <option key={room.id} value={room.id}>{room.room_name}</option>)}
                </select>
                <button className="rounded-lg bg-[#2A5C8D] px-3 py-2 text-white disabled:opacity-50" disabled={busy || !selectedRoomId || (selectedPlaylist.tracks || []).length === 0} onClick={appendToRoom} type="button">追加到听歌房队列</button>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
