import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (relativePath) => readFileSync(new URL(`../${relativePath}`, import.meta.url), 'utf8')
const roomList = read('src/pages/SyncRoomList.jsx')
const sidebar = read('src/features/video/VideoRoomSidebar.jsx')
const shell = read('src/components/layout/AppShell.jsx')
const css = read('src/index.css')
const player = read('src/features/music/MusicRoomPlayer.jsx')
const page = read('src/pages/MineradioPage.jsx')

assert.match(roomList, /const payload = \{ room_name: roomName \}/, '创建观影房必须只提交房间名称')
assert.doesNotMatch(roomList.match(/const handleCreateRoom[\s\S]*?const handleJoinRoom/)?.[0] || '', /video_source|control_mode|password/, '创建表单不得提交房内设置')
for (const label of ['网络地址', '上传视频', '本地同步']) assert.match(sidebar, new RegExp(label))
assert.match(sidebar, /MP4、WebM、MOV、Ogg 和 HLS/)
assert.match(shell, /const showHeader = !isTransferDomain && !isAuthPage[\s\S]*!isAdminRoute/)
assert.match(shell, /const showFooter = !isTransferDomain && !isHome && !isToolbox[\s\S]*!isAdminRoute/)
assert.match(shell, /const hasWideNavigation = !isTransferDomain &&/)
assert.match(css, /--surface-page:\s*#fff/)
assert.match(css, /--shadow-card:\s*none/)

assert.match(player, /class NativeAudioAdapter/)
assert.match(player, /function ParticleField\s*\(/)
assert.match(player, /normalizeLyrics/)
assert.match(player, /听歌房音频播放器/)
assert.match(player, /在线成员与聊天/)
assert.match(player, /历史听歌记录/)
assert.match(page, /<MusicRoomPlayer/)
assert.doesNotMatch(player, /postMessage|contentWindow|<iframe/i)
assert.doesNotMatch(page, /\/mineradio-api|postMessage|contentWindow|<iframe/i)

console.log('native music room experience source checks passed')
