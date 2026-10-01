import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const player = readFileSync(new URL('../src/features/music/MusicRoomPlayer.jsx', import.meta.url), 'utf8')
const searchPanel = readFileSync(new URL('../src/features/music/MusicRoomSearchPanel.jsx', import.meta.url), 'utf8')
const page = readFileSync(new URL('../src/pages/MineradioPage.jsx', import.meta.url), 'utf8')
const actions = readFileSync(new URL('../src/features/music/musicRoomActions.js', import.meta.url), 'utf8')
const config = readFileSync(new URL('../src/config.js', import.meta.url), 'utf8')

test('room search is rendered by the native React player and calls the FastAPI catalog', () => {
  assert.match(player, /<MusicRoomSearchPanel onAction=\{onRoomAction\} \/>/)
  assert.match(searchPanel, /API_ENDPOINTS\.MUSIC_SEARCH/)
  assert.match(searchPanel, /provider, q: value/)
  assert.match(searchPanel, /propose-native-search/)
  assert.match(searchPanel, /网易云/)
  assert.match(searchPanel, /QQ 音乐/)
  assert.match(config, /MUSIC_SEARCH/)
})

test('native search selection only proposes a room queue item', () => {
  assert.match(actions, /action === 'propose-native-search'/)
  assert.doesNotMatch(searchPanel, /postMessage|contentWindow|<iframe/i)
  assert.doesNotMatch(player, /postMessage|contentWindow|<iframe/i)
  assert.doesNotMatch(`${page}\n${actions}`, /\/mineradio-api|postMessage|contentWindow|<iframe/i)
})

console.log('native music search source checks passed')
