import PlayerStage from '../features/player/PlayerStage.jsx'
import { demoTrack } from '../features/player/demoTrack.js'

export default function StandalonePlayerPage() {
  return (
    <main className="route-shell standalone-player-route">
      <header className="route-shell__intro standalone-player-route__intro">
        <p className="route-shell__eyebrow">音乐 · 本地模式</p>
        <h1>无需音乐平台的本地试听</h1>
        <p>
          此演示完全使用本地生成的 WAV 音频，不会连接曲库、账户服务、听歌房或远程音频主机。
        </p>
      </header>
      <PlayerStage track={demoTrack} />
    </main>
  )
}
