import { useEffect, useMemo, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'

function playlistFrom(response) {
  return response?.data?.playlist || response?.data
}

export function useMusicPlaylistManager() {
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

  const selectPlaylist = (playlistId) => {
    setSelectedPlaylistId(playlistId)
    setRenaming(false)
  }

  const startRename = () => {
    setRenameValue(selectedPlaylist.name)
    setRenaming((value) => !value)
  }

  const changeSourceReference = (value) => {
    setSourceReference(value)
    setImportPreview(null)
  }

  return {
    addTrack,
    appendToRoom,
    busy,
    changeSourceReference,
    confirmImport,
    createPlaylist,
    deletePlaylist,
    error,
    importPreview,
    moveTrack,
    newName,
    notice,
    playlists,
    previewImport,
    removeTrack,
    renameValue,
    renaming,
    rooms,
    saveRename,
    searchQuery,
    searchResults,
    searchTracks,
    selectedPlaylist,
    selectedRoomId,
    selectPlaylist,
    setNewName,
    setRenameValue,
    setSearchQuery,
    setSelectedRoomId,
    sourceReference,
    startRename,
  }
}
