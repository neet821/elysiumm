import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const source = new URL('../src/', import.meta.url)
const pagePath = new URL('pages/SyncRoomList.jsx', source)
const controllerPath = new URL('features/video/useSyncRoomListController.js', source)
const lobbyPath = new URL('features/video/useSyncRoomLobby.js', source)
const roomCardPath = new URL('features/video/SyncRoomCard.jsx', source)
const createModalPath = new URL('features/video/SyncRoomCreateModal.jsx', source)
const roomListUtilsPath = new URL('features/video/syncRoomListUtils.js', source)
const roomShareUtilsPath = new URL('features/video/roomShareUtils.js', source)
const page = readFileSync(pagePath, 'utf8')
const controller = readFileSync(controllerPath, 'utf8')

test('sync room page delegates room data and HTTP operations to its feature hook', () => {
  assert.ok(existsSync(lobbyPath), 'the video feature must own the sync-room lobby hook')
  assert.match(page, /useSyncRoomListController/)
  assert.match(controller, /useSyncRoomLobby/)
  assert.doesNotMatch(page, /from ['"]\.\.\/utils\/request['"]|apiClient\.(get|post|put|delete)/)

  const lobby = readFileSync(lobbyPath, 'utf8')
  assert.match(lobby, /API_ENDPOINTS\.SYNC_ROOMS/)
  assert.match(lobby, /API_ENDPOINTS\.SYNC_ROOM_JOIN/)
  assert.match(lobby, /API_ENDPOINTS\.ADMIN_ROOM_LOCK/)
  assert.match(lobby, /export function buildSyncRoomPayload/)
})

test('sync room page composes feature-owned card and create-modal views', () => {
  assert.ok(existsSync(roomCardPath), 'room-card presentation must live in the video feature')
  assert.ok(existsSync(createModalPath), 'create-modal presentation must live in the video feature')
  assert.ok(page.includes('import SyncRoomCard'), 'page must import the room-card view')
  assert.ok(page.includes('import SyncRoomCreateModal'), 'page must import the create-modal view')
  assert.doesNotMatch(page, /const RoomCard\s*=/)
  assert.doesNotMatch(page, /\{showCreateModal && \(/)
})

test('video feature owns its room-list and room-share utilities', () => {
  assert.ok(existsSync(roomListUtilsPath), 'room-list helpers must live in the video feature')
  assert.ok(existsSync(roomShareUtilsPath), 'room-share helpers must live in the video feature')
  assert.ok(!page.includes('roomShareUtils.js'), 'page must not own the room-share utility')
  assert.ok(!page.includes('syncRoomListUtils.js'), 'page must not own the room-list utility')
  assert.match(controller, /roomShareUtils\.js/)

  const roomCard = readFileSync(roomCardPath, 'utf8')
  assert.match(roomCard, /syncRoomListUtils\.js/)
  assert.doesNotMatch(roomCard, /from ['"].*pages\//)
})
