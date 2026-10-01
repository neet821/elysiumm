import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const page = readFileSync(new URL('../src/pages/MineradioPage.jsx', import.meta.url), 'utf8')
const controller = readFileSync(
  new URL('../src/features/music/useMusicRoomPageController.js', import.meta.url),
  'utf8',
)

test('music room page composes a feature controller instead of owning room operations', () => {
  assert.match(page, /useMusicRoomPageController/)
  for (const pageOperation of [
    'loadMusicRoomData',
    'createMusicRoomActionHandler',
    'useMusicRoomRealtime',
    'useMusicRoomPlaybackSync',
    'apiClient',
  ]) {
    assert.doesNotMatch(page, new RegExp(pageOperation))
  }
  for (const featureOperation of [
    'loadMusicRoomData',
    'createMusicRoomActionHandler',
    'useMusicRoomRealtime',
    'useMusicRoomPlaybackSync',
  ]) {
    assert.match(controller, new RegExp(featureOperation))
  }
})
