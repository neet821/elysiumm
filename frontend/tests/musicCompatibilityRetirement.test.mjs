import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const sourceDir = new URL('../src/', import.meta.url)
const compatibilityPath = new URL('features/player/MineradioRoomEmbed.jsx', sourceDir)
const roomPage = readFileSync(new URL('pages/MineradioPage.jsx', sourceDir), 'utf8')

test('the retired Mineradio bridge import path is not shipped', () => {
  assert.equal(existsSync(compatibilityPath), false)
  assert.match(roomPage, /import MusicRoomPlayer from ['"]\.\.\/features\/music\/MusicRoomPlayer\.jsx['"]/)
  assert.doesNotMatch(roomPage, /MineradioRoomEmbed/)
})
