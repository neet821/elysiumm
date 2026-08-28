import SyncRoomList from './SyncRoomList.jsx'
import { THEME } from '../theme.js'

export default function MusicLobbyPage({ embedded = false }) {
  return <SyncRoomList embedded={embedded} isDark={false} roomMode="music" styles={THEME.light} />
}
