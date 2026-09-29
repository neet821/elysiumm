import { useNavigate, useParams } from 'react-router-dom'

import { useAuth } from '../contexts/AuthContext'
import MusicRoomPlayer from '../features/music/MusicRoomPlayer.jsx'
import { useMusicRoomPageController } from '../features/music/useMusicRoomPageController.js'

export default function MineradioPage() {
  const { roomId } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const {
    handleAdapterReady,
    handlePlayerEvent,
    handleRoomAction,
    loading,
    playerTrack,
    resolvedCurrent,
    room,
    roomState,
  } = useMusicRoomPageController({ navigate, roomId, user })

  if (loading || !room) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">
        <p role="status">正在进入听歌房…</p>
      </main>
    )
  }

  return (
    <div className="music-room-immersive" data-room-id={roomId}>
      <h1 className="sr-only">听歌房</h1>
      <section className="music-room-shell__stage" aria-label="房间播放器">
        <MusicRoomPlayer
          onAdapterReady={handleAdapterReady}
          onEvent={handlePlayerEvent}
          onRoomAction={handleRoomAction}
          playerTrack={playerTrack}
          roomId={roomId}
          roomState={roomState}
          track={resolvedCurrent}
        />
      </section>
    </div>
  )
}
