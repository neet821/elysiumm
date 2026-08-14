import { Copy, LogOut, RefreshCw, Users } from 'lucide-react'
import { useParams, useNavigate } from 'react-router-dom'

import { useAuth } from '../contexts/AuthContext.jsx'
import VideoRoomSidebar from '../features/video/VideoRoomSidebar.jsx'
import VideoStage from '../features/video/VideoStage.jsx'
import { useVideoRoom } from '../features/video/useVideoRoom.js'


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

  if (authLoading || loading || !room) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">
        <p role="status">正在进入视频房…</p>
      </main>
    )
  }

  return (
    <main className={`${isDark ? 'bg-slate-950 text-slate-100' : 'bg-slate-100 text-slate-900'} min-h-screen pt-[4.5rem]`}>
      <header className="sticky top-[4.25rem] z-20 border-b border-slate-200/80 bg-white/90 px-4 py-3 backdrop-blur dark:border-slate-700 dark:bg-slate-950/90">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3">
          <button type="button" onClick={leave} className="rounded-lg p-2" aria-label="退出房间"><LogOut size={18} /></button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-bold">{room.room_name}</h1>
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
              <span>房间号 {room.room_code}</span>
              <button type="button" aria-label="复制房间号" onClick={() => navigator.clipboard?.writeText(room.room_code)}><Copy size={13} /></button>
              <span>{room.control_mode === 'host_only' ? '房主控制' : '全员控制'}</span>
            </div>
          </div>
          <span className="flex items-center gap-1 text-sm"><Users size={16} />{members.filter((member) => member.is_online !== false).length}</span>
          <span role="status" className="rounded-full bg-slate-200 px-3 py-1 text-xs dark:bg-slate-800">
            {STATUS_LABELS[syncStatus] || STATUS_LABELS.connecting}
          </span>
          <button type="button" onClick={requestSnapshot} className="rounded-lg p-2" aria-label="重新同步"><RefreshCw size={17} /></button>
        </div>
      </header>

      {notice && (
        <div className="mx-auto mt-3 max-w-[1600px] px-4">
          <p role="status" className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100">{notice}</p>
        </div>
      )}

      <div className="mx-auto grid max-w-[1600px] gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <VideoStage roomState={roomState} />
        <VideoRoomSidebar roomState={roomState} />
      </div>
    </main>
  )
}
