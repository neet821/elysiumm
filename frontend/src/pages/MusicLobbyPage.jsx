import { useState } from 'react'
import SyncRoomList from './SyncRoomList.jsx'
import MusicPlaylistManager from '../features/music/MusicPlaylistManager.jsx'
import { THEME } from '../theme.js'
import '../features/music/musicLobby.css'

export default function MusicLobbyPage() {
  const [tab, setTab] = useState('rooms')
  const switchWithKeyboard = (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const next = event.key === 'Home' ? 'rooms' : event.key === 'End' ? 'playlists' : tab === 'rooms' ? 'playlists' : 'rooms'
    setTab(next)
    event.currentTarget.parentElement.querySelector(`[aria-controls="music-lobby-${next}"]`)?.focus()
  }
  return (
    <div className="music-lobby">
      <nav className="music-lobby__tabs" role="tablist" aria-label="音乐大厅分区" onKeyDown={switchWithKeyboard}>
        <button id="music-lobby-rooms-tab" role="tab" aria-controls="music-lobby-rooms" aria-selected={tab === 'rooms'} tabIndex={tab === 'rooms' ? 0 : -1} onClick={() => setTab('rooms')}>一起听</button>
        <button id="music-lobby-playlists-tab" role="tab" aria-controls="music-lobby-playlists" aria-selected={tab === 'playlists'} tabIndex={tab === 'playlists' ? 0 : -1} onClick={() => setTab('playlists')}>我的歌单</button>
      </nav>
      <div className="music-lobby__grid">
        <section id="music-lobby-rooms" role="tabpanel" aria-labelledby="music-lobby-rooms-tab" data-active={tab === 'rooms'}>
          <SyncRoomList isDark={false} roomMode="music" styles={THEME.light} />
        </section>
        <section id="music-lobby-playlists" className="music-lobby__playlists" role="tabpanel" aria-labelledby="music-lobby-playlists-tab" data-active={tab === 'playlists'}>
          <MusicPlaylistManager />
        </section>
      </div>
    </div>
  )
}
