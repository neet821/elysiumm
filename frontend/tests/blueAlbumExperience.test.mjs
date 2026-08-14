import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const roomList = readFileSync(new URL('../src/pages/SyncRoomList.jsx', import.meta.url), 'utf8')
const sidebar = readFileSync(new URL('../src/features/video/VideoRoomSidebar.jsx', import.meta.url), 'utf8')
const shell = readFileSync(new URL('../src/components/layout/AppShell.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
const bridge = readFileSync(new URL('../../mineradio/public/blue-album-room-bridge.js', import.meta.url), 'utf8')

assert.match(roomList, /const payload = \{ room_name: roomName \}/, '创建观影房必须只提交房间名称')
assert.doesNotMatch(roomList.match(/const handleCreateRoom[\s\S]*?const handleJoinRoom/)?.[0] || '', /video_source|control_mode|password/, '创建表单不得提交房内设置')
for (const label of ['网络地址', '上传视频', '本地同步']) assert.match(sidebar, new RegExp(label))
assert.match(sidebar, /MP4、WebM、MOV、Ogg 和 HLS/)
assert.match(shell, /isMusicRoom[\s\S]*?!isMusicRoom && <Header/)
assert.match(shell, /!isToolbox && !isMusicRoom && <Footer/)
assert.match(css, /--surface-page:\s*#fff/)
assert.match(css, /--shadow-card:\s*none/)
assert.doesNotMatch(bridge, />ONLINE<|>PRIVATE SYNC<|>ROOMS<|USER ID/)
for (const label of ['返回首页', '离开房间', '重新同步', '房间成员', '实时聊天', '搜索点歌', '上传共享音频', '房间公共歌单']) {
  assert.match(bridge, new RegExp(label), `Mineradio 房间桥接必须包含 ${label}`)
}

console.log('plain service experience source checks passed')
