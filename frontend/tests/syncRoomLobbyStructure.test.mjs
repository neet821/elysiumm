import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const source = new URL('../src/', import.meta.url)
const pagePath = new URL('pages/SyncRoomList.jsx', source)
const lobbyPath = new URL('features/video/useSyncRoomLobby.js', source)
const page = readFileSync(pagePath, 'utf8')

test('sync room page delegates room data and HTTP operations to its feature hook', () => {
  assert.ok(existsSync(lobbyPath), 'the video feature must own the sync-room lobby hook')
  assert.match(page, /useSyncRoomLobby/)
  assert.doesNotMatch(page, /from ['"]\.\.\/utils\/request['"]|apiClient\.(get|post|put|delete)/)

  const lobby = readFileSync(lobbyPath, 'utf8')
  assert.match(lobby, /API_ENDPOINTS\.SYNC_ROOMS/)
  assert.match(lobby, /API_ENDPOINTS\.SYNC_ROOM_JOIN/)
  assert.match(lobby, /API_ENDPOINTS\.ADMIN_ROOM_LOCK/)
  assert.match(lobby, /export function buildSyncRoomPayload/)
})
