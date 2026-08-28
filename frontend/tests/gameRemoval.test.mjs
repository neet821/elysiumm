import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'

const root = new URL('../src/', import.meta.url)
const read = (relativePath) => readFileSync(new URL(relativePath, root), 'utf8')

const routesSource = read('routes.jsx')
const navigationSource = read('navigation.js')
const toolboxSource = read('pages/toolEntries.js')
const homeSource = read('pages/ContentHomePage.jsx')

assert.doesNotMatch(routesSource, /GameRoomPage|GameDetailPage|GamesPage|RoomsGamesPage|path=['"]\/(?:games|rooms\/games)/, '游戏页面和路由必须移除')
assert.doesNotMatch(navigationSource, /桌游|\/games/, '主导航不得保留桌游入口')
assert.doesNotMatch(toolboxSource, /Gamepad2|桌游|\/games/, '工具箱不得保留桌游入口')
assert.doesNotMatch(homeSource, /桌游|\/rooms['"]/, '首页不得保留旧房间聚合入口或桌游入口')
assert.match(homeSource, /观影房/)
assert.match(homeSource, /听歌房/)

for (const path of ['pages/GamesPage.jsx', 'pages/GameDetailPage.jsx', 'pages/GameRoomPage.jsx', 'pages/RoomsGamesPage.jsx', 'pages/RoomsPage.jsx']) {
  assert.equal(existsSync(new URL(path, root)), false, `${path} 必须删除`)
}
