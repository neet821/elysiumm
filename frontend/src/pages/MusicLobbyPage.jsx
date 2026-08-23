import SyncRoomList from './SyncRoomList.jsx'
import { THEME } from '../theme.js'

export default function MusicLobbyPage() {
  return <SyncRoomList isDark={false} roomMode="music" styles={THEME.light} />
}
