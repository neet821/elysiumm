import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'

const root = path.basename(process.cwd()) === 'frontend' ? path.resolve(process.cwd(), '..') : process.cwd()
const bridge = fs.readFileSync(path.join(root, 'mineradio/public/blue-album-room-bridge.js'), 'utf8')
const queueActions = fs.readFileSync(path.join(root, 'mineradio/public/js/modules/05-playback/10-queue-actions.js'), 'utf8')
const search = fs.readFileSync(path.join(root, 'mineradio/public/js/modules/05-playback/07-search.js'), 'utf8')

test('room mode keeps Mineradio native search visible with disabled placeholders', () => {
  assert.doesNotMatch(bridge, /blue-album-room-mode #search-area[^}]*display:\s*none/)
  assert.match(bridge, /#search-area[^}]*display:\s*(?:flex|block)/)
  for (const id of ['search-mode-kugou', 'search-mode-qishui', 'search-mode-spotify', 'search-mode-podcast']) {
    assert.match(bridge, new RegExp(`#${id}[^}]*display\\s*:\\s*none`))
  }
  assert.match(bridge, /qq\.disabled = true/)
  assert.match(bridge, /blue-room-search-mode-other/)
})

test('native search selection is routed to the room instead of Mineradio local playback', () => {
  assert.match(queueActions, /__BLUE_ROOM_NATIVE_SEARCH_SELECT/)
  assert.match(bridge, /propose-native-search/)
  assert.match(bridge, /provider_track_id/)
})

test('room search results keep the native renderer but hide personal actions', () => {
  assert.match(search, /blue-album-room-mode/)
  assert.match(search, /roomMode \? '' : .*toggleLikeSearchResult/s)
  assert.match(search, /roomMode \? '' : .*collectSearchResult/s)
  assert.match(search, /\(roomMode \? '' : '<button class="add-btn"/)
  assert.doesNotMatch(search, /roomMode \? '加入房间公共歌单'/)
})
