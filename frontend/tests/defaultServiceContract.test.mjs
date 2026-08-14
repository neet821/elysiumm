import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const root = new URL('../src/', import.meta.url)
const read = (name) => readFileSync(new URL(name, root), 'utf8')

test('service shell is explicit and fixed to the plain light presentation', () => {
  const shell = read('components/layout/AppShell.jsx')
  const css = read('index.css')

  assert.match(shell, /service-shell|ServiceShell/)
  assert.match(css, /\.service-shell/)
  assert.match(css, /--surface-page:\s*#fff/i)
  assert.match(css, /--text-primary:\s*#111/i)
})

test('formal header does not expose the legacy theme switch', () => {
  const header = read('components/Header.jsx')
  assert.doesNotMatch(header, /app-header__theme/)
  assert.doesNotMatch(header, /toggleTheme/)
  assert.match(header, /工具箱/)
})

test('formal navigation uses Elysium copy while old brand stays isolated', () => {
  const navigation = read('navigation.js')
  assert.match(navigation, /Elysium/)
  assert.match(navigation, /SERVICE_DIRECTORY/)
  assert.doesNotMatch(navigation, /Blue Album/)
})

test('toolbox keeps the four plain directory groups', () => {
  const navigation = read('navigation.js')
  const tools = read('pages/ToolsPage.jsx')
  assert.match(navigation, /公开服务/)
  assert.match(navigation, /协作房间/)
  assert.match(navigation, /个人内容/)
  assert.match(navigation, /管理入口/)
  assert.match(tools, /全部服务/)
})

test('the room stylesheet cannot lock scrolling on formal pages', () => {
  const room = read('features/elysium-room/room.css')
  assert.doesNotMatch(room, /html,\s*body,\s*#app\s*\{[^}]*overflow:\s*hidden/s)
  assert.match(room, /:has\(\.app-shell--home\)/)
})

test('the 3D home top bar uses the Elysium plain header treatment', () => {
  const home = read('features/elysium-room/ElysiumRoomHome.jsx')
  const styles = read('features/elysium-room/elysiumRoom.css')
  assert.match(home, /elysium-room-home__brand/)
  assert.match(home, /elysium-mark\.svg/)
  assert.match(styles, /elysium-room-home__topbar[\s\S]*background:\s*rgb\(255 255 255/)
  assert.match(styles, /elysium-room-home__nav a[\s\S]*background:\s*#111/)
})
