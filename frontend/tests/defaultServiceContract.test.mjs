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

test('the 3D home reuses the compact formal header and keeps its mode control at the bottom', () => {
  const shell = read('components/layout/AppShell.jsx')
  const home = read('features/elysium-room/ElysiumRoomHome.jsx')
  const experience = read('pages/homeExperience.css')
  assert.match(shell, /!isMusicRoom\s*&&\s*<Header \/>/)
  assert.doesNotMatch(home, /elysium-room-home__topbar/)
  assert.doesNotMatch(home, /NAV_ITEMS/)
  assert.match(experience, /home-experience__mode-switch[\s\S]*bottom:/)
  assert.doesNotMatch(experience, /home-experience__mode-switch[\s\S]*top:/)
  assert.match(read('features/elysium-room/ui/createHud.js'), /aria-label="显示模式"/)
})
