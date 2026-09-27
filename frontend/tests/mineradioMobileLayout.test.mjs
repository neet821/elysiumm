import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const player = readFileSync(new URL('../src/features/music/MusicRoomPlayer.jsx', import.meta.url), 'utf8')
const page = readFileSync(new URL('../src/pages/MineradioPage.jsx', import.meta.url), 'utf8')
const queuePanel = readFileSync(new URL('../src/features/music/MusicRoomQueuePanel.jsx', import.meta.url), 'utf8')
const searchPanel = readFileSync(new URL('../src/features/music/MusicRoomSearchPanel.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('../src/features/music/musicRoom.css', import.meta.url), 'utf8')
const globalCss = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
const roomExperience = `${page}\n${player}\n${queuePanel}\n${searchPanel}`

test('native room player has responsive visual, lyric, and queue surfaces', () => {
  assert.match(player, /import ['"]\.\/musicRoom\.css['"]/, 'the music feature must own its stylesheet')
  for (const token of [
    'music-room-immersive',
    'music-room-shell__stage',
    'music-room-native',
    'music-room-native__visual',
    'music-room-native__lyrics',
    'music-room-native__particles',
    'music-room-native__panel',
    'music-room-native__search',
  ]) {
    assert.match(roomExperience, new RegExp(token))
    assert.match(css, new RegExp(`\\.${token.replaceAll('__', '__')}`))
    assert.doesNotMatch(globalCss, new RegExp(`\\.${token.replaceAll('__', '__')}`))
  }
  assert.match(css, /@media\s*\(/)
  assert.match(css, /music-room-native__lower/)
})

test('native player does not require the old standalone Mineradio service', () => {
  assert.doesNotMatch(player, /\/mineradio-api|\/mineradio\/|3000|3100|postMessage|<iframe/i)
  assert.doesNotMatch(`${css}\n${globalCss}`, /mineradio-room-embed iframe/)
})

console.log('native music room responsive source checks passed')
