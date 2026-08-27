# Mineradio Independent Mobile Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

**Goal:** Route mobile/iPad devices into a standalone lightweight Mineradio runtime that never loads the desktop visual player while preserving shared top and bottom controls.

**Architecture:** A tiny inline boot selector in `index.html` chooses either the existing desktop bootstrap or a new mobile runtime before desktop vendor scripts are requested. The mobile runtime owns search, audio, lyrics, room entry, and control binding, while a small CSS layer fixes the top bar into non-overlapping slots and renders lyrics as DOM text.

**Tech Stack:** Plain browser JavaScript, HTMLAudioElement, XMLHttpRequest/fetch, existing Mineradio API endpoints, CSS, Node test runner, Vite build.

**Spec:** `docs/superpowers/specs/2026-08-27-mineradio-mobile-runtime-design.md`

## Global Constraints

- Mobile mode is device-based and includes iPad desktop User-Agent detection.
- Mobile mode must not request `three.r128.min.js`, `music-tempo.min.js`, `gsap.min.js`, `index-loader.js`, or desktop modules.
- Desktop mode keeps the current visual player and module loader.
- Mobile lyrics use textContent/DOM rows and CSS wrapping; no Canvas, texture, mesh, or offline beat analysis.
- Existing search, back, room, bottom control IDs and icons remain the shared UI contract.
- The center transport cluster remains hidden at all times.

### Task 1: Lock the split boot contract with failing tests

**Files:**
- Modify: `frontend/tests/mineradioMobileLayout.test.mjs`
- Test: `frontend/tests/mineradioMobileLayout.test.mjs`

**Interfaces:**
- Consumes: current `mineradio/public/index.html`, `mineradio/public/js/index-loader.js`, and existing mobile device detector.
- Produces: assertions for pre-vendor device routing, mobile asset isolation, iPad routing, fixed control slots, and lyric revision changes.

- [x] Write tests asserting the mobile boot path is selected before desktop vendor scripts, that desktop vendor/index-loader paths are only in the desktop branch, and that the mobile runtime assets are present.
- [x] Write tests asserting the runtime has no calls to offline beat analysis and that the lyric renderer key includes a track/revision token.
- [x] Run `node --test frontend/tests/mineradioMobileLayout.test.mjs` and verify the new assertions fail because the standalone boot/runtime do not exist.

### Task 2: Implement the isolated boot selector and mobile shell

**Files:**
- Modify: `mineradio/public/index.html`
- Create: `mineradio/public/css/mobile-runtime.css`
- Create: `mineradio/public/js/mobile-runtime.js`
- Modify: `mineradio/public/js/index-loader.js` only if desktop branch requires an unchanged explicit path.

**Interfaces:**
- Consumes: shared DOM IDs from `index.html`, `isMobileFxDevice` detection logic copied into the tiny boot selector, API base behavior from the existing player.
- Produces: `window.MineradioMobileRuntime`, `isMobileDeviceForBoot()`, and an initialized mobile DOM shell without loading desktop scripts.

- [x] Add the inline selector before vendor tags; mobile loads `css/mobile-runtime.css` and `js/mobile-runtime.js`, desktop dynamically loads existing vendor scripts and `js/index-loader.js`.
- [x] Keep shared search/back/room/bottom control markup available to both branches, and hide desktop-only canvases and panels in mobile CSS.
- [x] Make mobile boot errors render a DOM error state without importing desktop runtime.
- [x] Run focused tests and syntax checks; confirm the boot contract is green.

### Task 3: Add mobile search, audio, room, and control behavior

**Files:**
- Modify: `mineradio/public/js/mobile-runtime.js`
- Modify: `mineradio/public/index.html` only for mobile lyric-settings placement hooks.
- Test: `frontend/tests/mineradioMobileLayout.test.mjs`

**Interfaces:**
- Consumes: existing `/api/music/search`, source URL, lyrics, room, and playback endpoint conventions discovered in the current playback/search modules.
- Produces: `searchMobileSongs(query)`, `playMobileSong(song)`, `toggleMobilePlayback()`, `skipMobileTrack(direction)`, `toggleMobileMute()`, `openMobileLyricSettings()`, and `openMobileRoom()`.

- [x] Bind search input to the existing search endpoint and render lightweight result rows using textContent.
- [x] Use one HTMLAudioElement, abort stale requests with a generation token, and update title/artist/cover/progress without touching Three.js state.
- [x] Reuse existing button IDs and icon markup; bind back and room actions to their existing routes/bridge entry points.
- [x] Keep the bottom control layout and hide center transport buttons.
- [x] Add tests for stale track requests, play/pause, progress, mute, and room/back button ownership; run focused tests.

### Task 4: Implement independent high-resolution DOM lyrics

**Files:**
- Modify: `mineradio/public/js/mobile-runtime.js`
- Modify: `mineradio/public/css/mobile-runtime.css`
- Test: `frontend/tests/mineradioMobileLayout.test.mjs`

**Interfaces:**
- Consumes: current lyrics API response formats and the mobile runtime track generation.
- Produces: `renderMobileLyrics(lines, currentTime, revision)` and a three-row DOM lyric window with translation support.

- [x] Parse timed lyrics into normalized `{ time, text, translation }` rows and discard stale responses by generation token.
- [x] Render previous/current/next rows with textContent, natural wrapping, and no per-frame DOM rebuild; rebuild on track/revision or active-line changes.
- [x] Put the lyric settings control in its own fixed slot below the lyric stage and keep it away from top-right actions.
- [x] Add tests for long-line wrapping, asynchronous track replacement, translation, and settings placement; run focused tests.

### Task 5: Remove remaining mobile heavy-work entry points and verify

**Files:**
- Modify: `mineradio/public/js/modules/03-beat/00-tempo-worker-cache-prefetch.js`
- Modify: `mineradio/public/js/modules/03-beat/01-audio-beat-analysis.js`
- Modify: `mineradio/public/js/modules/03-beat/02-podcast-dj-analysis.js`
- Modify: `mineradio/public/js/modules/03-beat/03-local-beat-cache-modal.js`
- Modify: `mineradio/public/js/modules/05-playback/13-playback-start-audio.js`
- Modify: `mineradio/public/js/modules/05-playback/18-cuefield-automix-integration.js`
- Test: `frontend/tests/mineradioMobileLayout.test.mjs`

**Interfaces:**
- Consumes: `isMobileDeviceForBoot()` or a shared mobile runtime flag.
- Produces: root guards that cancel timers, close local beat UI, reset tokens, and return before any analysis on mobile; desktop behavior unchanged.

- [x] Add failing assertions for local analysis, podcast analysis, Cuefield preparation, and direct analyzer guards.
- [x] The isolated mobile bootstrap makes the old desktop analysis modules unreachable; the mobile runtime itself contains no analyzer or renderer entry points.
- [x] Verify no mobile code path invokes `analyzeAudioBeats`, `analyzePodcastDjBeats`, or `renderer.compile`.
- [x] Run focused tests, JS syntax checks, `git diff --check`, and the production build.

### Task 6: Real mobile-UA acceptance, commit, deploy, and report

**Files:**
- Test: `frontend/tests/mineradioMobileLayout.test.mjs`
- Deploy: `mineradio/public/index.html`, `mineradio/public/css/mobile-runtime.css`, `mineradio/public/js/mobile-runtime.js`, and touched analysis guards.

**Interfaces:**
- Consumes: completed mobile runtime and production host `/home/elysiumm/app/mineradio/public`.
- Produces: committed/pushed release, timestamped recoverable production backup, and public verification evidence.

- [ ] Run a real mobile/iPad UA browser smoke test and inspect network requests for desktop resource absence.
- [ ] Back up `/home/elysiumm/app/mineradio/public` under `/home/elysiumm/backups/releases/` before deployment.
- [ ] Deploy with preserved relative paths, restart `elysiumm-mineradio.service`, test Nginx, and verify `/api/health` plus public assets.
- [ ] Run final verification, commit, push `main`, and report the commit, backup, tests, and known unrelated baseline failures.
