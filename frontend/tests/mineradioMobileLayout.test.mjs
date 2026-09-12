import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const player = readFileSync(new URL('../src/features/music/MusicRoomPlayer.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')

test('native room player has responsive visual, lyric, and queue surfaces', () => {
  for (const token of [
    'music-room-native',
    'music-room-native__visual',
    'music-room-native__lyrics',
    'music-room-native__particles',
    'music-room-native__panel',
    'music-room-native__search',
  ]) {
    assert.match(player, new RegExp(token))
    assert.match(css, new RegExp(`\\.${token.replaceAll('__', '__')}`))
  }
  assert.match(css, /@media\s*\(/)
  assert.match(css, /music-room-native__lower/)
})

test('native player does not require the old standalone Mineradio service', () => {
  assert.doesNotMatch(player, /\/mineradio-api|\/mineradio\/|3000|3100|postMessage|<iframe/i)
  assert.doesNotMatch(css, /mineradio-room-embed iframe/)
})

console.log('native music room responsive source checks passed')
