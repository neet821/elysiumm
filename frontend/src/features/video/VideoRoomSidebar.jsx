import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, Film, Link2, MessageCircle, Settings, Trash2, Upload, Users } from 'lucide-react'


export default function VideoRoomSidebar({ roomState }) {
  const {
    addUrl,
    addLocalVideo,
    advance,
    buffers,
    busy,
    canControl,
    currentItem,
    chooseLocalVideo,
    deleteItem,
    deleteSubtitle,
    isHost,
    localReady,
    kickMember,
    members,
    messages,
    reorder,
    selectItem,
    sendMessage,
    session,
    uploadSubtitle,
    uploadVideo,
    transferHost,
    updateRoomSettings,
    userId,
  } = roomState
  const [url, setUrl] = useState('')
  const [chat, setChat] = useState('')
  const [subtitleLabel, setSubtitleLabel] = useState('中文')
  const [subtitleLanguage, setSubtitleLanguage] = useState('zh-CN')
  const [messageTarget, setMessageTarget] = useState('')
  const [sourceMode, setSourceMode] = useState('url')
  const [roomName, setRoomName] = useState(roomState.room?.room_name || '')

  useEffect(() => {
    setRoomName(roomState.room?.room_name || '')
  }, [roomState.room?.room_name])

  const move = (index, offset) => {
    const nextIndex = index + offset
    if (nextIndex < 0 || nextIndex >= session.playlist.length) return
    const ids = session.playlist.map((item) => item.id)
    ;[ids[index], ids[nextIndex]] = [ids[nextIndex], ids[index]]
    reorder(ids)
  }

  return (
    <aside className="grid min-w-0 gap-4 xl:grid-rows-[auto_auto_1fr]">
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-3 flex items-center gap-2 font-semibold"><Film size={18} />片单</h2>
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
              <Link2 size={15} /> 添加到片单
            </button>}
            {sourceMode === 'upload' && <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600">
              <Upload size={16} /> 上传视频
              <input
                className="sr-only"
                type="file"
                accept="video/mp4,video/webm,video/quicktime,video/ogg,.m4v"
                disabled={busy}
                onChange={(event) => event.target.files?.[0] && uploadVideo(event.target.files[0])}
              />
            </label>}
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
        <ol className="max-h-64 space-y-2 overflow-y-auto">
          {session.playlist.map((item, index) => (
            <li
              key={item.id}
              className={`rounded-xl border p-2 ${item.id === currentItem?.id ? 'border-sky-500 bg-sky-50 dark:bg-sky-950/30' : 'border-slate-200 dark:border-slate-700'}`}
            >
              <button
                type="button"
                disabled={!canControl || item.id === currentItem?.id}
                onClick={() => selectItem(item.id)}
                className="w-full truncate text-left text-sm font-medium disabled:cursor-default"
              >
                {index + 1}. {item.title}
              </button>
              <span className="mt-1 inline-flex rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                {item.source_type === 'legacy_local' ? '本地同步' : item.playback_kind === 'hls' ? 'HLS 流媒体' : item.source_type === 'upload' ? '服务器上传' : '网络地址'}
              </span>
              {canControl && (
                <div className="mt-2 flex gap-1">
                  <button type="button" aria-label={`上移 ${item.title}`} onClick={() => move(index, -1)} disabled={index === 0 || busy} className="rounded p-1 disabled:opacity-30"><ArrowUp size={14} /></button>
                  <button type="button" aria-label={`下移 ${item.title}`} onClick={() => move(index, 1)} disabled={index === session.playlist.length - 1 || busy} className="rounded p-1 disabled:opacity-30"><ArrowDown size={14} /></button>
                  <button type="button" aria-label={`删除 ${item.title}`} onClick={() => deleteItem(item.id)} disabled={busy} className="ml-auto rounded p-1 text-rose-600 disabled:opacity-30"><Trash2 size={14} /></button>
                </div>
              )}
            </li>
          ))}
        </ol>
        {canControl && currentItem && (
          <button type="button" onClick={advance} disabled={busy} className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600">
            播放下一项
          </button>
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

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-3 flex items-center gap-2 font-semibold"><Users size={18} />在线成员</h2>
        <ul className="grid gap-2 text-sm">
          {members.map((member) => (
            <li key={member.user_id} className="flex flex-wrap items-center justify-between gap-2">
              <span className={member.is_online === false ? 'text-slate-400' : ''}>{member.username}</span>
              <span className="text-xs text-slate-500">{currentItem?.source_type === 'legacy_local' ? (localReady[member.user_id]?.ready && localReady[member.user_id]?.item_id === currentItem.id ? '本地文件已准备' : '等待选择本地文件') : buffers[member.user_id] ? '缓冲中' : member.is_online === false ? '离线' : '在线'}</span>
              {isHost && String(member.user_id) !== String(userId) && (
                <span className="flex basis-full justify-end gap-2 text-xs">
                  <button type="button" onClick={() => transferHost(member.user_id)} className="text-sky-700 dark:text-sky-300">转让房主</button>
                  <button type="button" onClick={() => kickMember(member.user_id)} className="text-rose-600">移出房间</button>
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="flex min-h-72 flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-3 flex items-center gap-2 font-semibold"><MessageCircle size={18} />聊天</h2>
        <div className="min-h-40 flex-1 space-y-2 overflow-y-auto" aria-live="polite">
          {messages.map((message) => (
            <p key={message.id} className="rounded-lg bg-slate-100 px-3 py-2 text-sm dark:bg-slate-800">
              <strong>{message.username || message.user || '成员'}：</strong>{message.message || message.text}
            </p>
          ))}
        </div>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (sendMessage(chat, messageTarget ? Number(messageTarget) : null)) setChat('')
          }}
        >
          <div className="min-w-0 flex-1 space-y-2">
            <select aria-label="消息接收人" value={messageTarget} onChange={(event) => setMessageTarget(event.target.value)} className="w-full rounded-lg border border-slate-300 bg-transparent px-2 py-1 text-xs dark:border-slate-600">
              <option value="">所有成员</option>
              {members.filter((member) => String(member.user_id) !== String(userId)).map((member) => (
                <option key={member.user_id} value={member.user_id}>私信 {member.username}</option>
              ))}
            </select>
            <input aria-label="聊天消息" value={chat} onChange={(event) => setChat(event.target.value)} maxLength={500} className="w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm dark:border-slate-600" />
          </div>
          <button type="submit" className="rounded-lg bg-sky-600 px-3 py-2 text-sm text-white">发送</button>
        </form>
      </section>
    </aside>
  )
}
