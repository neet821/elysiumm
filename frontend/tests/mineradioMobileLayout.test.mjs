import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'

const root = path.resolve(new URL('../..', import.meta.url).pathname)
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const html = read('mineradio/public/index.html')
const css = read('mineradio/public/css/index.css')
const archive = read('mineradio/public/js/modules/07-fx/00-preset-archive-data.js')
const bindings = read('mineradio/public/js/modules/07-fx/07-bindings-shelf-immersive.js')
const peekPanels = read('mineradio/public/js/modules/10-shell/02-peek-panels-upload.js')
const lyricMask = read('mineradio/public/js/modules/02-visual/10-lyrics-mask-textures.js')
const mobile2dLyrics = read('mineradio/public/js/modules/02-visual/15-mobile-2d-lyrics.js')
const startup = read('mineradio/public/js/modules/10-shell/05-startup-bindings.js')
const mainLoop = read('mineradio/public/js/modules/11-main-loop.js')
const playbackStart = read('mineradio/public/js/modules/05-playback/13-playback-start-audio.js')
const beatChip = read('mineradio/public/js/modules/03-beat/03-local-beat-cache-modal.js')
const loader = read('mineradio/public/js/index-loader.js')
const mobileRuntime = read('mineradio/public/js/mobile-runtime.js')
const mobileRuntimeCss = read('mineradio/public/css/mobile-runtime.css')
const desktopSplash = read('mineradio/public/js/modules/10-shell/03-splash.js')
const sonicMonitor = read('mineradio/public/js/modules/03-beat/06-sonic-audio-monitor.js')
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

test('player mode is device-based and keeps iPad in the mobile profile', () => {
  assert.match(archive, /userAgent/)
  assert.match(archive, /maxTouchPoints/)
  assert.match(archive, /iPadDesktopUa/)
  assert.match(archive, /if \(iPadDesktopUa \|\| iPadUa\) return true/)
  assert.match(archive, /desktop-player/)
  assert.doesNotMatch(archive, /matchMedia\('\\(max-width: 720px\\)'\)/)
})

test('player never renders the center transport controls', () => {
  assert.match(html, /class="control-cluster transport"/)
  assert.match(css, /#controls\s*>\s*\.control-cluster\.transport[^}]*display:\s*none\s*!important/s)
  assert.match(css, /#controls[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*1fr\)\s*!important/s)
  assert.doesNotMatch(css, /body\.desktop-player[^}]*#play-btn[^}]*display:\s*(?:flex|inline-flex)\s*!important/s)
})

test('mobile lyrics wrap an overlong current line into visual rows', () => {
  assert.match(lyricMask, /function wrapMobileLyricEntries\s*\(/)
  assert.match(lyricMask, /wrapLyricText\(/)
  assert.match(lyricMask, /MOBILE_LYRIC_MAX_LINES\s*=\s*3/)
})

test('multiline lyric textures reserve a full top ascent safety area', () => {
  assert.match(lyricMask, /LYRIC_MASK_TOP_PADDING_RATIO/)
  assert.match(lyricMask, /blockTop\s*=\s*y0\s*-\s*fontSize\s*\*\s*LYRIC_MASK_TOP_PADDING_RATIO/)
  assert.match(lyricMask, /padY\s*=\s*Math\.max\(/)
})

test('mobile exposes a dedicated lyrics typography entry without restoring the full visual console', () => {
  assert.match(html, /id="mobile-lyric-settings-btn"/)
  assert.match(html, /onclick="openMobileLyricSettings\(event\)"/)
  assert.match(css, /body\.mobile-device #mobile-lyric-settings-btn[^}]*display:\s*(?:flex|inline-flex)\s*!important/s)
  assert.match(bindings, /function openMobileLyricSettings\s*\(/)
  assert.match(bindings, /setFxPanelTab\('lyrics'\)/)
  assert.match(peekPanels, /key === 'fx' && !\(document\.body && document\.body\.classList\.contains\('mobile-device'\)\)/)
  assert.match(css, /body\.mobile-device #fx-fab[^}]*display:\s*none\s*!important/s)
})

test('mobile preset keeps lyrics sharp while disabling high-cost visual work', () => {
  assert.match(archive, /function normalizeMobileFxForPerformance\s*\(/)
  assert.match(archive, /performanceQuality\s*=\s*'eco'/)
  assert.match(archive, /lyricTextureClarity\s*=\s*4/)
  assert.match(archive, /particleLyrics\s*=\s*false/)
  assert.match(archive, /sonicAudioMonitorEnabled\s*=\s*false/)
  assert.match(archive, /sonicGroundFloatingCount\s*=\s*0/)
  assert.match(archive, /coverResolution\s*=\s*1/)
})

test('mobile Mineradio applies the named archive and hides visual controls', () => {
  assert.match(archive, /function applyMobileFxArchiveForDevice\s*\(/)
  assert.match(archive, /var MOBILE_FX_ARCHIVE_NAME = '移动端'/)
  assert.match(archive, /item\.name === MOBILE_FX_ARCHIVE_NAME/)
  assert.match(startup, /applyMobileFxArchiveForDevice\(\)/)
  assert.match(css, /body\.mobile-device #fx-fab[^}]*display:\s*none\s*!important/)
  assert.match(css, /body\.mobile-device #fx-fab-hide-btn[^}]*display:\s*none\s*!important/)
})

test('mobile 2D mode has a dedicated DOM lyric surface and bypasses 3D lyric work', () => {
  assert.match(html, /id="mobile-2d-stage"/)
  assert.match(html, /id="mobile-2d-lyrics"/)
  assert.match(loader, /02-visual\/15-mobile-2d-lyrics\.js/)
  assert.match(mobile2dLyrics, /function updateMobile2dLyrics\s*\(/)
  assert.match(mobile2dLyrics, /textContent/)
  assert.match(css, /body\.mobile-2d-ui #mobile-2d-stage[^}]*display:\s*flex/s)
  assert.match(css, /body\.mobile-2d-ui #canvas-container[^}]*display:\s*none\s*!important/s)
  assert.match(mainLoop, /isMobile2dUi\(\)/)
  assert.match(mainLoop, /updateMobile2dLyrics\(/)
})

test('mobile 2D mode never starts beat analysis or leaves the beat chip visible', () => {
  assert.match(playbackStart, /isMobileFxDevice\(\)/)
  assert.match(playbackStart, /else if \(podcastDjMode\)/)
  assert.match(beatChip, /isMobile2dUi\(\)/)
  assert.match(beatChip, /hideBeatChip\(\)/)
  assert.match(mainLoop, /var mobile2d = isMobile2dUi\(\)/)
})

test('mobile boot selects a standalone runtime before desktop vendor scripts', () => {
  assert.match(html, /function isMobileDeviceForBoot\s*\(/)
  assert.match(html, /mobile-runtime\.css/)
  assert.match(html, /mobile-runtime\.js/)
  assert.match(html, /mobile-runtime\.css\?v=20260827-mobile-runtime-3/)
  assert.match(html, /mobile-runtime\.js\?v=20260827-mobile-runtime-3/)
  assert.match(html, /blue-album-room-bridge\.js\?v=20260827-room-history-2/)
  assert.match(html, /loadDesktopRuntime\s*\(/)
  assert.doesNotMatch(html, /<script[^>]+(?:three\.r128|music-tempo|gsap|index-loader)/)
  assert.doesNotMatch(html, /<link[^>]+css\/index\.css/)
  assert.match(mobileRuntime, /window\.MineradioMobileRuntime/)
  assert.match(mobileRuntime, /function mobileApiUrl\s*\(/)
  assert.match(mobileRuntime, /\/mineradio-api\//)
  assert.doesNotMatch(mobileRuntime, /THREE|OfflineAudioContext|analyzeAudioBeats|analyzePodcastDjBeats/)
})

test('desktop runtime binds late-loaded splash and beat controls after DOMContentLoaded', () => {
  assert.match(desktopSplash, /function bindMineradioSplashInteractions\s*\(/)
  assert.match(desktopSplash, /if \(document\.readyState === 'loading'\)[\s\S]*else\s*{\s*bindMineradioSplashInteractions\(\)/)
  assert.match(sonicMonitor, /if \(document\.readyState === 'loading'\)[\s\S]*else\s*{\s*bindSonicAudioMonitorControls\(\)/)
})

test('standalone mobile runtime renders lyrics and owns fixed top slots without desktop overlap', () => {
  assert.match(mobileRuntime, /function renderMobileLyrics\s*\(/)
  assert.match(mobileRuntime, /textContent/)
  assert.match(mobileRuntime, /trackGeneration|lyricRevision/)
  assert.match(mobileRuntime, /__BLUE_ROOM_NATIVE_SEARCH_SELECT/)
  assert.match(mobileRuntime, /if \(!isRoomMode\(\)\) nextTrack/)
  assert.match(mobileRuntime, /yrc/)
  assert.match(mobileRuntime, /removeAttribute\('onclick'\)/)
  assert.match(mobileRuntimeCss, /\.mobile-runtime-top[^}]*grid-template-columns/s)
  assert.match(mobileRuntimeCss, /\.mobile-runtime-lyric-settings[^}]*position:\s*fixed/s)
  assert.match(mobileRuntimeCss, /\.mobile-runtime-controls[^}]*position:\s*fixed/s)
  assert.match(mobileRuntimeCss, /transport[^}]*#volume-control/s)
})

test('iPad mobile chrome keeps top controls on one 46px baseline with a fixed 8px gap', () => {
  assert.match(mobileRuntimeCss, /--mobile-runtime-top-control-size:\s*46px;/)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active #top-right\s*\{[^}]*width:\s*var\(--mobile-runtime-top-control-size\) !important;/)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active #search-area\s*\{[^}]*left:\s*calc\(14px \+ var\(--mobile-runtime-top-control-size\) \+ var\(--mobile-runtime-top-control-gap\)\) !important;[^}]*right:\s*calc\(14px \+ var\(--mobile-runtime-top-control-size\) \+ var\(--mobile-runtime-top-control-gap\)\) !important;/)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active #home-btn,[\s\S]*?height:\s*var\(--mobile-runtime-top-control-size\);/)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active #search-box\s*\{[^}]*height:\s*46px !important;/)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active #bottom-bar\.mobile-runtime-controls #progress-fill\s*\{[^}]*background:\s*#fff;/)
  assert.match(mobileRuntimeCss, /\.mobile-runtime-setting-row input\s*\{[^}]*accent-color:\s*#fff;/)
})

test('standalone mobile runtime preserves room, cover, progress, and volume interactions', () => {
  assert.match(mobileRuntime, /mobileApiUrl\([^)]*\/api\/cover/)
  assert.match(mobileRuntime, /volumeControl\.classList\.toggle\('is-open'/)
  assert.match(mobileRuntime, /classList\.toggle\('is-muted'/)
  assert.match(mobileRuntime, /setAttribute\('aria-pressed'/)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active #blue-room-btn[^}]*pointer-events:\s*auto/s)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active #bottom-bar\.mobile-runtime-controls #progress-fill[^}]*height:\s*100%/s)
  assert.match(mobileRuntimeCss, /#volume-control\.is-open \.volume-popover[^}]*display:\s*grid/s)
})

test('standalone mobile lyrics move the active line with playback', () => {
  assert.match(mobileRuntime, /function positionMobileLyrics\s*\(/)
  assert.match(mobileRuntime, /mobile-runtime-lyric-track/)
  assert.match(mobileRuntime, /translate3d\(0,.*lyricShift/)
  assert.match(mobileRuntimeCss, /\.mobile-runtime-lyric-track[^}]*transition:\s*transform/s)
})

test('standalone mobile lyrics align after async loading and progress stays display-only', () => {
  assert.match(mobileRuntime, /state\.lyricIndex = -1;\s*renderMobileLyrics\(\);\s*updateLyricCursor\(true\)/s)
  assert.match(mobileRuntimeCss, /\.control-cover[^}]*background-size:\s*cover/s)
  assert.match(mobileRuntimeCss, /#progress-thumb[^}]*display:\s*none\s*!important/s)
  assert.match(mobileRuntimeCss, /#progress-bar[^}]*pointer-events:\s*none/s)
  assert.doesNotMatch(mobileRuntime, /if \(progress\) progress\.addEventListener\('click'/)
})

test('mobile lyrics keep original and translation in separate rows with automatic sizing', () => {
  assert.match(mobileRuntime, /mobile-runtime-lyric-original/)
  assert.match(mobileRuntime, /mobile-runtime-lyric-translation/)
  assert.doesNotMatch(mobileRuntime, /lyric\.text \+ \(lyric\.translation \? '\\n' \+ lyric\.translation : ''\)/)
  assert.match(mobileRuntimeCss, /\.mobile-runtime-lyric-original[^}]*display:\s*block/s)
  assert.match(mobileRuntimeCss, /\.mobile-runtime-lyric-translation[^}]*display:\s*block/s)
  assert.match(mobileRuntimeCss, /--mobile-runtime-lyric-size/s)
  assert.match(mobileRuntimeCss, /clamp\(/)
  assert.doesNotMatch(mobileRuntime, /lyric\.time/)
})

test('mobile runtime derives a cover-colored background and makes immersive mode functional', () => {
  assert.match(mobileRuntime, /function updateMobileRuntimeBackground\s*\(/)
  assert.match(mobileRuntime, /canvas|getContext\(['"]2d['"]\)/)
  assert.match(mobileRuntime, /mobile-runtime-bg-primary/)
  assert.match(mobileRuntime, /mobile-runtime-immersive/)
  assert.match(mobileRuntime, /aria-pressed/)
  assert.match(mobileRuntimeCss, /mobile-runtime-immersive[^}]*#search-area/s)
  assert.match(mobileRuntimeCss, /mobile-runtime-immersive[^}]*#bottom-bar/s)
  assert.match(mobileRuntimeCss, /mobile-runtime-immersive[^}]*#mobile-2d-stage/s)
})

test('mobile runtime uses one refined liquid-glass language for chrome and controls', () => {
  assert.match(mobileRuntimeCss, /--mobile-runtime-glass-/)
  assert.match(mobileRuntimeCss, /#search-box[^}]*backdrop-filter:\s*blur/s)
  assert.match(mobileRuntimeCss, /#home-btn[^}]*backdrop-filter:\s*blur/s)
  assert.match(mobileRuntimeCss, /#bottom-bar\.mobile-runtime-controls[^}]*backdrop-filter:\s*blur/s)
  assert.match(mobileRuntimeCss, /-webkit-backdrop-filter:\s*blur/)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active\s*:is\([^}]+\):active[^}]*transform:\s*scale\(\.97\)/s)
})

test('mobile lyrics are not paint-clipped by upper and lower chrome', () => {
  assert.match(mobileRuntimeCss, /\.mobile-runtime-lyrics[^}]*overflow:\s*visible/s)
  assert.match(mobileRuntimeCss, /\.mobile-runtime-lyrics[^}]*contain:\s*layout\s*;/s)
  assert.doesNotMatch(mobileRuntimeCss, /\.mobile-runtime-lyrics[^}]*contain:\s*layout\s+paint/s)
})

test('immersive mode hides search, lyric tools, and the control bar with a tap-to-exit surface', () => {
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active\.mobile-runtime-immersive \.mobile-runtime-lyric-tools[^}]*visibility:\s*hidden/s)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active\.mobile-runtime-immersive #bottom-bar\.mobile-runtime-controls[^}]*opacity:\s*0/s)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active\.mobile-runtime-immersive #bottom-bar\.mobile-runtime-controls[^}]*pointer-events:\s*none/s)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active\.mobile-runtime-immersive #mobile-2d-stage[^}]*pointer-events:\s*auto/s)
  assert.match(mobileRuntime, /stage\.addEventListener\('click'/)
})

test('immersive mode keeps a mirrored exit button at the original control position', () => {
  assert.match(mobileRuntime, /function createImmersiveExitButton\s*\(/)
  assert.match(mobileRuntime, /immersive\.cloneNode\(true\)/)
  assert.match(mobileRuntime, /mobile-runtime-immersive-exit/)
  assert.match(mobileRuntime, /exitButton\.addEventListener\('click'/)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active\.mobile-runtime-immersive #mobile-runtime-immersive-exit[^}]*visibility:\s*visible/s)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active:not\(.mobile-runtime-immersive\) #mobile-runtime-immersive-exit[^}]*visibility:\s*hidden/s)
})

test('the listening-room return button shares the desktop and mobile glass control treatment', () => {
  assert.match(bridge, /leaveButton\.className\s*=\s*'icon-btn player-return-control'/)
  assert.match(css, /#blue-room-leave\.player-return-control[^}]*var\(--saved-button-glass-bg\)/s)
  assert.match(css, /#blue-room-leave\.player-return-control:hover[^}]*var\(--saved-button-glass-hover-bg\)/s)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active #blue-room-leave\.player-return-control[^}]*var\(--mobile-runtime-glass-fill\)/s)
  assert.match(mobileRuntimeCss, /body\.mobile-runtime-active #blue-room-leave\.player-return-control:hover[^}]*var\(--mobile-runtime-glass-highlight\)/s)
})

test('mobile 2D top actions use fixed, non-overlapping slots and collapse account pills', () => {
  assert.match(css, /body\.mobile-2d-ui #top-right[^}]*pointer-events:\s*none/s)
  assert.match(css, /body\.mobile-2d-ui #top-right > #home-btn[^}]*left:\s*var\(--mobile-2d-side\)/s)
  assert.match(css, /body\.mobile-2d-ui #top-right > #mobile-lyric-settings-btn[^}]*right:\s*72px/s)
  assert.match(css, /body\.mobile-2d-ui #top-right > #user-btn[^}]*right:\s*max\(16px/s)
  assert.match(css, /body\.mobile-2d-ui #top-right > #user-btn\.multi-account\.external-account-pills[^}]*overflow:\s*hidden/s)
  assert.match(css, /body\.mobile-2d-ui #user-btn \.top-account-pill:not\(:first-child\)[^}]*display:\s*none\s*!important/s)
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

test('music room keeps its membership alive with a presence heartbeat', () => {
  assert.match(page, /presence_heartbeat/)
  assert.match(page, /setInterval\(.*presence_heartbeat/s)
})

test('music room history is collapsed, re-queueable, and rendered last', () => {
  assert.match(bridge, /class="br-history-fold"/)
  assert.match(bridge, /data-action="readd-history"/)
  assert.match(bridge, /data-history-id=/)
  assert.match(bridge, /historySection\s*\+\s*adminSection|adminSection\s*\+\s*historySection/)
  assert.match(page, /action === 'readd-history'/)
  assert.match(page, /MUSIC_HISTORY_REQUEUE/)
})

test('music room exposes controls to administrators and removes both favorite buttons', () => {
  assert.match(page, /const isAdmin = Boolean\(user && user\.role === 'admin'\)/)
  assert.match(page, /isHost \|\| isAdmin/)
  assert.match(bridge, /var isAdmin = !!roomState\.isAdmin/)
  assert.match(bridge, /isHost \|\| isAdmin/)
  assert.doesNotMatch(html, /id="heart-btn"/)
  assert.doesNotMatch(html, /id="collect-btn"/)
})
