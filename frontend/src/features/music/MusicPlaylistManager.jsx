import { useMusicPlaylistManager } from './useMusicPlaylistManager.js'

const availabilityLabel = {
  playable: '可播放',
  preview: '试听',
  unavailable: '不可用',
}

export default function MusicPlaylistManager() {
  const {
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
  } = useMusicPlaylistManager()

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
            <input className="mb-2 w-full rounded-lg border border-[var(--border-color)] bg-[var(--bg-color)] px-3 py-2" id="music-playlist-import-reference" onChange={(event) => changeSourceReference(event.target.value)} placeholder="粘贴歌单链接或 ID" value={sourceReference} />
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
                  <button aria-current={selectedPlaylist?.id === playlist.id ? 'page' : undefined} className="w-full rounded-lg px-3 py-2 text-left hover:bg-[var(--bg-color)] aria-[current=page]:bg-[var(--bg-color)]" onClick={() => selectPlaylist(playlist.id)} type="button">
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
                  <button className="rounded-lg border border-[var(--border-color)] px-3 py-2" onClick={startRename} type="button">重命名歌单</button>
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
