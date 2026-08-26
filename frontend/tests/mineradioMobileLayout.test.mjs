import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'

const root = path.resolve(new URL('../..', import.meta.url).pathname)
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const html = read('mineradio/public/index.html')
const css = read('mineradio/public/css/index.css')
const archive = read('mineradio/public/js/modules/07-fx/00-preset-archive-data.js')
const startup = read('mineradio/public/js/modules/10-shell/05-startup-bindings.js')
const bridge = read('mineradio/public/blue-album-room-bridge.js')
const volume = read('mineradio/public/js/modules/05-playback/08-audio-graph-controls.js')
const page = read('frontend/src/pages/MineradioPage.jsx')
const mobileDefault = JSON.parse(read('mineradio/public/mobile-default-user-fx-archive.json'))

const MOBILE_DEFAULT_SHARE_CODE = 'MR2:1.GH4sIAAAAAAAAA01Q0WrDQAz7F_dVDdadz3f-ltKHLEuWwkagTfv9I2k7ZoPARkiyT8RJPgUnIsNAsEA7M7CBnVckYr3eR6QMOfTx0YYmSAVymPohVAWpQg6qrZ8mQVbI7WdZ1lmQE6b--zbCCmQeLwJzHLVTg1Wwa7CGUEXxTYFbCzwhFC0_bVuBK5pD-vu6CFqFzJevWRB8qcfbhpYhw_IYrwIWQpYtEUuG3NZ-vQzb4G9yqfu1DQqW2NB1R-LIAvqfrBu0C7DVZyaGQjstYBDUTj3-Fxjx-pnuxGw1J1rKYWpsgaTc955DkzutaC6sfj6ffwHyPmPnkAEAAA.0VVB5Y2'

test('mobile profile is frozen and delivered by the server', () => {
  assert.equal(mobileDefault.name, '移动端')
  assert.equal(mobileDefault.shareCode, MOBILE_DEFAULT_SHARE_CODE)
  assert.match(archive, /mobile-default-user-fx-archive\.json/)
  assert.match(archive, /fetch\(MOBILE_FX_ARCHIVE_SERVER_URL/)
  assert.match(archive, /decodeUserFxArchiveShareCode/)
})

test('mobile Mineradio applies the named archive and hides visual controls', () => {
  assert.match(archive, /function applyMobileFxArchiveForDevice\s*\(/)
  assert.match(archive, /var MOBILE_FX_ARCHIVE_NAME = '移动端'/)
  assert.match(archive, /item\.name === MOBILE_FX_ARCHIVE_NAME/)
  assert.match(startup, /applyMobileFxArchiveForDevice\(\)/)
  assert.match(css, /body\.mobile-device #fx-fab[^}]*display:\s*none\s*!important/)
  assert.match(css, /body\.mobile-device #fx-fab-hide-btn[^}]*display:\s*none\s*!important/)
})

test('mobile controls keep track information and only volume plus immersive actions', () => {
  assert.match(html, /id="volume-btn"[^>]*onclick="toggleMute\(event\)"/)
  assert.match(css, /body\.mobile-device \.control-cluster\.modes \.lyrics-toggle-btn[^}]*display:\s*none\s*!important/)
  assert.match(css, /body\.mobile-device #controls-hide-btn[^}]*display:\s*none\s*!important/)
  assert.match(css, /body\.mobile-device \.fullscreen-toggle-btn[^}]*display:\s*none\s*!important/)
  assert.match(css, /body\.mobile-device \.control-track[^}]*display:\s*flex\s*!important/)
  assert.match(css, /body\.mobile-device \.control-cover[^}]*display:\s*block\s*!important/)
  assert.match(css, /body\.mobile-device \.control-cluster\.actions[^}]*grid-column:\s*1\s*!important/)
  assert.match(css, /body\.mobile-device \.control-cluster\.transport[^}]*grid-column:\s*2\s*!important/)
  assert.match(css, /body\.mobile-device \.control-cluster\.modes[^}]*grid-column:\s*3\s*!important/)
  assert.match(css, /body\.mobile-device \.control-cluster\.actions[^}]*order:\s*0/)
  assert.match(css, /body\.mobile-device \.control-cluster\.transport[^}]*order:\s*0/)
  assert.match(css, /body\.mobile-device \.control-cluster\.modes[^}]*order:\s*0/)
})

test('volume button uses the shared mute toggle and restores the last audible level', () => {
  assert.match(volume, /function toggleMute\s*\(e\)/)
  assert.match(volume, /setVolume\(targetVolume > 0\.01 \? 0 : \(lastNonZeroVolume \|\| 0\.8\)\)/)
})

test('mobile room button owns a fixed viewport hit area', () => {
  assert.match(bridge, /body\.blue-album-room-mode #top-right\{z-index:50!important\}/)
  assert.match(bridge, /@media\(max-width:720px\)\{.*#blue-room-btn\{position:fixed;/s)
  assert.match(bridge, /#blue-room-btn\{position:fixed;top:12px;right:12px;[^}]*z-index:50;/)
})

test('mobile room header keeps back and room controls on both sides of a compact search', () => {
  assert.match(bridge, /@media\(max-width:720px\)\{.*#blue-room-panel\{left:12px;right:12px!important;top:68px;/s)
  assert.match(bridge, /#blue-room-btn\{position:fixed;top:12px;right:12px;/)
  assert.match(bridge, /body\.blue-album-room-mode #search-area\{top:12px!important;left:68px!important;right:68px!important;width:auto!important;height:44px!important;transform:none!important\}/)
})

test('iPad-safe room transport prefers polling and acknowledges autoplay-blocked state', () => {
  assert.match(page, /transports:\s*\['polling', 'websocket'\]/)
  assert.match(bridge, /autoplay_blocked/)
  assert.match(bridge, /sync-applied/)
})
