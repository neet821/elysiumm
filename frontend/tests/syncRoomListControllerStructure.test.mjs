import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const page = readFileSync(new URL('../src/pages/SyncRoomList.jsx', import.meta.url), 'utf8')
const controller = readFileSync(
  new URL('../src/features/video/useSyncRoomListController.js', import.meta.url),
  'utf8',
)

test('sync room page delegates room actions and transient state to its feature controller', () => {
  assert.match(page, /useSyncRoomListController/)
  for (const pageOperation of [
    'useSyncRoomLobby',
    'buildRoomShareUrl',
    'copyText',
    'setInterval',
  ]) {
    assert.doesNotMatch(page, new RegExp(pageOperation))
  }
  assert.doesNotMatch(page, /const handle(?:CreateRoom|JoinRoom|DeleteRoom|ToggleRoomLock)\s*=/)
  for (const featureOperation of [
    'useSyncRoomLobby',
    'buildRoomShareUrl',
    'copyText',
    'createRoom',
    'joinRoom',
    'deleteRoom',
    'toggleRoomLock',
  ]) {
    assert.match(controller, new RegExp(featureOperation))
  }
})
