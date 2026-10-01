import SyncRoomList from './SyncRoomList.jsx'
import MusicPlaylistManager from '../features/music/MusicPlaylistManager.jsx'
import { THEME } from '../theme.js'

export default function MusicLobbyPage() {
  return (
    <>
      <SyncRoomList isDark={false} roomMode="music" styles={THEME.light} />
      <MusicPlaylistManager />
    </>
  )
}
