import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const player = readFileSync(new URL('../src/features/music/MusicRoomPlayer.jsx', import.meta.url), 'utf8')
const page = readFileSync(new URL('../src/pages/MineradioPage.jsx', import.meta.url), 'utf8')
const config = readFileSync(new URL('../src/config.js', import.meta.url), 'utf8')

test('room search is rendered by the native React player and calls the FastAPI catalog', () => {
  assert.match(player, /function SearchPanel\s*\(/)
  assert.match(player, /API_ENDPOINTS\.MUSIC_SEARCH/)
  assert.match(player, /provider: provider/)
  assert.match(player, /propose-native-search/)
  assert.match(player, /网易云/)
  assert.match(player, /QQ 音乐/)
  assert.match(config, /MUSIC_SEARCH/)
})

test('native search selection only proposes a room queue item', () => {
  assert.match(player, /onAction\(\{\s*action: 'propose-native-search'/s)
  assert.match(page, /action === 'propose-native-search'/)
  assert.doesNotMatch(player, /postMessage|contentWindow|<iframe/i)
  assert.doesNotMatch(page, /\/mineradio-api|postMessage|contentWindow|<iframe/i)
})

console.log('native music search source checks passed')
