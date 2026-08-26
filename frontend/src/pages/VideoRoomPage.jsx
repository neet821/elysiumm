import { Copy, LogOut, RefreshCw, Users } from 'lucide-react'
import { useParams, useNavigate } from 'react-router-dom'

import { useAuth } from '../contexts/AuthContext.jsx'
import VideoRoomSidebar from '../features/video/VideoRoomSidebar.jsx'
import VideoRoomCommunity from '../features/video/VideoRoomCommunity.jsx'
import VideoStage from '../features/video/VideoStage.jsx'
import { useVideoRoom } from '../features/video/useVideoRoom.js'
import { buildRoomShareUrl, copyText } from './roomShareUtils.js'


const STATUS_LABELS = {
  connecting: '正在连接…',
  error: '同步暂时失败',
  reconnecting: '连接中断，正在恢复…',
  synced: '已与服务器同步',
  syncing: '正在同步…',
}

export default function VideoRoomPage({ isDark = false }) {
  const { id } = useParams()
  const navigate = useNavigate()
  const { user, loading: authLoading } = useAuth()
  const roomState = useVideoRoom({ navigate, roomId: id, user })
  const { leave, loading, members, notice, requestSnapshot, room, syncStatus } = roomState
  const copyShareLink = async () => {
    try {
      await copyText(buildRoomShareUrl({ ...window.location, pathname: `/rooms/watch/${id}`, search: '', hash: '' }))
    } catch {
      // Clipboard access is optional; the URL remains visible in the browser.
    }
  }

  if (authLoading || loading || !room) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">
        <p role="status">正在进入视频房…</p>
      </main>
    )
  }

  return (
    <main className={`${isDark ? 'bg-slate-950 text-slate-100' : 'bg-slate-100 text-slate-900'} min-h-screen`}>
      <div className="mx-auto max-w-[1600px] p-4">
        <div
          role="toolbar"
          aria-label="观影房工具栏"
          className="mb-4 flex min-h-16 max-w-[1600px] flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm dark:border-slate-700 dark:bg-slate-900"
        >
          <div className="flex min-w-0 items-center gap-3">
            <button type="button" onClick={leave} className="rounded-lg p-2" aria-label="退出房间"><LogOut size={18} /></button>
            <div className="min-w-0">
              <h1 className="truncate text-lg font-bold">{room.room_name}</h1>
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                <button type="button" className="inline-flex items-center gap-1 rounded-md border border-sky-700 bg-sky-600 px-2 py-1 font-semibold text-white shadow-sm hover:bg-sky-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-700" aria-label="复制分享链接" onClick={copyShareLink}><Copy size={13} />复制分享链接</button>
                <span>{room.control_mode === 'host_only' ? '房主控制' : '全员控制'}</span>
              </div>
            </div>
          </div>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-3">
            <span className="flex items-center gap-1 text-sm"><Users size={16} />{members.filter((member) => member.is_online !== false).length}</span>
            <span role="status" className="rounded-full bg-slate-200 px-3 py-1 text-xs dark:bg-slate-800">
              {STATUS_LABELS[syncStatus] || STATUS_LABELS.connecting}
            </span>
            <button type="button" onClick={requestSnapshot} className="rounded-lg p-2" aria-label="重新同步"><RefreshCw size={17} /></button>
          </div>
        </div>

        {notice && (
          <div className="mb-4">
            <p role="status" className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100">{notice}</p>
          </div>
        )}

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="min-w-0 xl:col-start-1 xl:row-start-1">
            <VideoStage roomState={roomState} />
          </div>
          <div data-testid="video-room-community" className="order-2 min-w-0 xl:col-span-2 xl:col-start-1 xl:row-start-2">
            <VideoRoomCommunity roomState={roomState} />
          </div>
          <div className="order-3 min-w-0 xl:col-start-2 xl:row-start-1">
            <VideoRoomSidebar roomState={roomState} />
          </div>
        </div>
      </div>
    </main>
  )
}
