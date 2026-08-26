import { useEffect, useState } from 'react'
import { Film, Link2, Settings, Upload } from 'lucide-react'


function formatBytes(value) {
  const bytes = Math.max(0, Number(value) || 0)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}


export default function VideoRoomSidebar({ roomState }) {
  const {
    addUrl,
    addLocalVideo,
    busy,
    canControl,
    currentItem,
    chooseLocalVideo,
    deleteSubtitle,
    isHost,
    session,
    selectItem,
    uploadSubtitle,
    uploadVideo,
    updateRoomSettings,
    uploadProgress,
  } = roomState
  const [url, setUrl] = useState('')
  const [subtitleLabel, setSubtitleLabel] = useState('中文')
  const [subtitleLanguage, setSubtitleLanguage] = useState('zh-CN')
  const [sourceMode, setSourceMode] = useState('url')
  const [roomName, setRoomName] = useState(roomState.room?.room_name || '')
  const [uploadQueue, setUploadQueue] = useState([])

  useEffect(() => {
    setRoomName(roomState.room?.room_name || '')
  }, [roomState.room?.room_name])

  const queueUploads = async (files) => {
    const selected = Array.from(files || [])
    if (!selected.length) return
    setUploadQueue(selected.map((file) => ({ name: file.name, state: '等待上传' })))
    for (let index = 0; index < selected.length; index += 1) {
      const file = selected[index]
      setUploadQueue((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, state: '上传中' } : item))
      const result = await uploadVideo(file, Boolean(currentItem) || index > 0)
      setUploadQueue((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, state: result ? '已加入播放列表' : '上传失败' } : item))
      if (!result) break
    }
  }

  return (
    <aside className="grid min-w-0 gap-4 xl:grid-rows-[auto_auto_1fr]">
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-3 flex items-center gap-2 font-semibold"><Film size={18} />当前视频</h2>
        {canControl && (
          <div className="mb-4 grid gap-2">
            <div className="grid grid-cols-3 gap-1" aria-label="视频来源方式">
              {[["url", "网络地址"], ["upload", "上传视频"], ["local", "本地同步"]].map(([value, label]) => (
                <button key={value} type="button" className={`border px-2 py-2 text-xs ${sourceMode === value ? 'border-sky-500 bg-sky-50 text-sky-700 dark:bg-sky-950/30 dark:text-sky-200' : 'border-slate-200 dark:border-slate-700'}`} onClick={() => setSourceMode(value)}>{label}</button>
              ))}
            </div>
            {sourceMode === 'url' && <label className="text-xs text-slate-600 dark:text-slate-300">
              视频网址
              <input
                aria-label="视频网址"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://…"
                className="mt-1 w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm dark:border-slate-600"
              />
              <span className="mt-1 block text-[11px] leading-5 text-slate-500 dark:text-slate-400">
                支持 MP4、WebM、MOV、Ogg 和 HLS 文件直链，不支持普通视频网页。
              </span>
            </label>}
            {sourceMode === 'url' && <button
              type="button"
              disabled={busy || !url.trim()}
              onClick={async () => {
                const value = url.trim()
                if (await addUrl(value)) setUrl('')
              }}
              className="rounded-lg bg-sky-600 px-3 py-2 text-sm text-white disabled:opacity-40"
            >
              <Link2 size={15} /> 替换当前视频
            </button>}
            {sourceMode === 'upload' && <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600">
              <Upload size={16} /> 上传视频
              <input
                className="sr-only"
                type="file"
                multiple
                accept="video/mp4,video/webm,video/quicktime,video/ogg,.m4v"
                disabled={busy || uploadProgress?.active}
                onChange={(event) => queueUploads(event.target.files)}
              />
            </label>}
            {uploadQueue.length > 0 && (
              <div className="grid gap-1 rounded-lg border border-slate-200 p-2 text-xs dark:border-slate-700" aria-label="视频上传队列">
                {uploadQueue.map((item, index) => <div className="flex justify-between gap-2" key={`${item.name}-${index}`}><span className="truncate">{index + 1}. {item.name}</span><span className="shrink-0 text-slate-500">{item.state}</span></div>)}
              </div>
            )}
            {session.playlist.length > 0 && (
              <div className="grid gap-1 rounded-lg border border-slate-200 p-2 text-xs dark:border-slate-700" aria-label="视频选集">
                {session.playlist.map((item, index) => (
                  <button
                    type="button"
                    key={item.id}
                    onClick={() => selectItem(item.id, true)}
                    disabled={busy || item.id === session.current_item_id}
                    className={`flex items-center justify-between gap-2 rounded px-2 py-2 text-left ${item.id === session.current_item_id ? 'bg-sky-100 text-sky-800 dark:bg-sky-950/50 dark:text-sky-200' : 'hover:bg-slate-100 dark:hover:bg-slate-800'}`}
                  >
                    <span className="truncate">第 {index + 1} 集 · {item.title}</span>
                    <span className="shrink-0">{item.id === session.current_item_id ? '播放中' : '播放'}</span>
                  </button>
                ))}
              </div>
            )}
            {uploadProgress?.active && (
              <div className="grid gap-1" aria-live="polite">
                <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-300">
                  <span>正在上传视频</span>
                  <span>{uploadProgress.percent}%</span>
                </div>
                <progress
                  aria-label="视频上传进度"
                  aria-valuemax="100"
                  aria-valuemin="0"
                  aria-valuenow={uploadProgress.percent}
                  className="h-2 w-full accent-sky-600"
                  max="100"
                  value={uploadProgress.percent}
                />
                <span className="text-[11px] text-slate-500 dark:text-slate-400">
                  {formatBytes(uploadProgress.loaded)} / {formatBytes(uploadProgress.total)}
                </span>
              </div>
            )}
            {sourceMode === 'local' && <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600">
              <Film size={16} /> 登记本地视频
              <input className="sr-only" type="file" accept="video/*,.mkv,.m4v,.mov,.ogv" disabled={busy} onChange={(event) => event.target.files?.[0] && addLocalVideo(event.target.files[0])} />
            </label>}
            {sourceMode === 'local' && <p className="text-[11px] leading-5 text-slate-500">只登记文件指纹，文件内容不会上传。其他成员需要各自选择同一个文件。</p>}
          </div>
        )}
        {currentItem?.source_type === 'legacy_local' && !currentItem.playback_url && (
          <label className="mb-4 flex cursor-pointer items-center justify-center gap-2 border border-amber-400 bg-amber-50 px-3 py-3 text-sm text-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
            选择房间要求的本地视频
            <input className="sr-only" type="file" accept="video/*,.mkv,.m4v,.mov,.ogv" disabled={busy} onChange={(event) => event.target.files?.[0] && chooseLocalVideo(currentItem, event.target.files[0])} />
          </label>
        )}
        {currentItem ? (
          <div className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm dark:border-sky-900 dark:bg-sky-950/30">
            <p className="truncate font-medium text-slate-800 dark:text-slate-100">{currentItem.title}</p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {currentItem.source_type === 'legacy_local' ? '本地同步播放' : currentItem.source_type === 'upload' ? '服务器上传视频' : currentItem.playback_kind === 'hls' ? 'HLS 流媒体' : '网络视频'}
            </p>
          </div>
        ) : (
          <p className="rounded-xl border border-dashed border-slate-300 px-3 py-4 text-sm text-slate-500 dark:border-slate-700">还没有当前视频，请先选择一个视频来源。</p>
        )}
        {canControl && currentItem && (
          <div className="mt-4 border-t border-slate-200 pt-3 dark:border-slate-700">
            <p className="mb-2 text-xs font-medium">为当前视频添加字幕</p>
            <div className="grid grid-cols-2 gap-2">
              <input aria-label="字幕名称" value={subtitleLabel} onChange={(event) => setSubtitleLabel(event.target.value)} className="rounded-lg border border-slate-300 bg-transparent px-2 py-1 text-xs dark:border-slate-600" />
              <input aria-label="字幕语言" value={subtitleLanguage} onChange={(event) => setSubtitleLanguage(event.target.value)} className="rounded-lg border border-slate-300 bg-transparent px-2 py-1 text-xs dark:border-slate-600" />
            </div>
            <label className="mt-2 flex cursor-pointer items-center justify-center rounded-lg border border-slate-300 px-2 py-2 text-xs dark:border-slate-600">
              选择 SRT / VTT
              <input
                className="sr-only"
                type="file"
                accept=".srt,.vtt,text/vtt,application/x-subrip"
                onChange={(event) => event.target.files?.[0] && uploadSubtitle(
                  currentItem.id,
                  event.target.files[0],
                  subtitleLabel,
                  subtitleLanguage,
                )}
              />
            </label>
            {session.selected_subtitle_id && (
              <button type="button" onClick={() => deleteSubtitle(session.selected_subtitle_id)} className="mt-2 w-full rounded-lg px-2 py-1 text-xs text-rose-600">
                删除当前字幕
              </button>
            )}
          </div>
        )}
      </section>

      {isHost && (
        <section className="border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <h2 className="mb-3 flex items-center gap-2 font-semibold"><Settings size={18} />房间设置</h2>
          <label className="mb-3 grid gap-2 text-sm">
            房间名称
            <span className="flex gap-2">
              <input className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-transparent px-3 py-2 dark:border-slate-600" maxLength={100} value={roomName} onChange={(event) => setRoomName(event.target.value)} />
              <button type="button" className="border border-slate-300 px-3 py-2 text-xs dark:border-slate-600" disabled={busy || !roomName.trim() || roomName.trim() === roomState.room?.room_name} onClick={() => updateRoomSettings({ room_name: roomName.trim() })}>保存</button>
            </span>
          </label>
          <label className="grid gap-2 text-sm">
            控制权限
            <select className="rounded-lg border border-slate-300 bg-transparent px-3 py-2 dark:border-slate-600" value={roomState.room?.control_mode || 'host_only'} onChange={(event) => updateRoomSettings({ control_mode: event.target.value })}>
              <option value="host_only">仅房主控制</option>
              <option value="all_members">所有成员控制</option>
            </select>
          </label>
        </section>
      )}

    </aside>
  )
}
