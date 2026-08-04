# Elysium 3D Room Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a lightweight, fully navigable Three.js personal room matching the approved fixed-camera, line-art, environment, and interaction requirements.

**Architecture:** A vanilla Vite application owns one Three.js runtime. Focused modules create outlined primitives and room zones, while independent camera, environment, interaction, audio, and route controllers coordinate through a small application entry point.

**Tech Stack:** Vite, JavaScript modules, Three.js, Vitest, Playwright

## Global Constraints

- Use simple Three.js geometry with light fills and dark outlines; do not depend on high-detail 3D models.
- Optimize the three fixed camera compositions rather than unseen room geometry.
- Camera changes must be smooth, 0.8 to 2 seconds, and never expose free orbit controls.
- Desktop targets are 1920x1080 and 2560x1440; common 16:9 and 16:10 screens must remain composed.
- Cap pixel ratio and avoid unnecessary shadows, post-processing, and high-poly meshes.
- Keep palette values centralized so later recoloring does not require room rewrites.

---

### Task 1: Runtime foundation and deterministic state

**Files:**
- Create: `package.json`, `index.html`, `src/main.js`, `src/styles.css`
- Create: `src/environment/environmentState.js`, `src/environment/palette.js`
- Test: `tests/environmentState.test.js`

**Interfaces:**
- Produces: `classifyLocalHour(hour)`, `createEnvironmentState(nowProvider)`, palette presets keyed by environment mode.

- [ ] Write unit tests proving hour boundaries and AUTO/manual override semantics.
- [ ] Run `npm test -- --run tests/environmentState.test.js` and confirm the missing module fails.
- [ ] Add Vite configuration, the application shell, environment state, and centralized palettes.
- [ ] Run the unit test and `npm run build`; both must pass.

### Task 2: Outlined geometry and room shell

**Files:**
- Create: `src/scene/createScene.js`, `src/scene/primitives.js`, `src/scene/textureLoader.js`
- Create: `src/room/createRoom.js`, `src/room/createShell.js`, `src/room/createBayWindow.js`
- Create: `public/scenery/nature.svg`, `city.svg`, `cloudy.svg`, `night.svg`

**Interfaces:**
- Consumes: palette object from Task 1.
- Produces: `createScene(canvas)`, `createOutlinedMesh(geometry, materialKey)`, `createRoom(context)`, room registry entries for interactive objects.

- [ ] Implement a material registry whose `applyPalette(palette)` updates every existing fill and edge material.
- [ ] Build the visible floor, trims, partial walls, bay window, frames, and one seamless outside plane.
- [ ] Add four local scenery assets and load them through one URL map with safe fallback.
- [ ] Run `npm run build` and open the base page; verify the shell renders without console errors.

### Task 3: Desk, right wall, and personal details

**Files:**
- Create: `src/room/createDeskZone.js`, `src/room/createRecordZone.js`, `src/room/createDecor.js`

**Interfaces:**
- Produces named groups and proxies: `monitor`, `lamp`, `recordPlayer`, `recordRack`, `photoWall`, `books`, `moviePoster`, and `window`.

- [ ] Build the long desk, monitor, stand, keyboard, lamp, chair, plant, and desktop objects from primitives.
- [ ] Build the low cabinet, record player, spinning record, tonearm, album rack, shelves, books/CDs, framed poster, and photo grid.
- [ ] Add restrained details such as floor boards, cables, pots, labels, and wall art to remove test-scene appearance.
- [ ] Inspect the overview scene and adjust scale/placement until its visual balance follows the supplied image.

### Task 4: Fixed camera rig

**Files:**
- Create: `src/camera/cameraPresets.js`, `src/camera/CameraRig.js`, `src/camera/easing.js`
- Test: `tests/camera.test.js`

**Interfaces:**
- Produces: `setPreset(name, options)`, `focus(targetPose)`, `restore()`, `update(delta, pointer)`, and `isTransitioning`.

- [ ] Test that all three presets and focus poses are finite and that easing endpoints are exact.
- [ ] Implement position/look-target interpolation and clamped pointer parallax with no OrbitControls.
- [ ] Tune overview, desk, and right-wall poses at 16:9 and 16:10.
- [ ] Verify each transition takes 0.8 to 2 seconds and finishes at the exact target pose.

### Task 5: Environment, lamp, and audio

**Files:**
- Create: `src/environment/EnvironmentController.js`, `src/audio/RoomAudio.js`

**Interfaces:**
- Consumes: scene lights/material registry/scenery mesh and state from Task 1.
- Produces: `setTimeMode(mode)`, `cycleScenery()`, `toggleLamp()`, `toggleRecord()`, and subscribable state snapshots.

- [ ] Connect AUTO and manual time modes to palette, lighting, background, scenery choice, and labels.
- [ ] Add warm lamp light/glow and update its visible geometry state.
- [ ] Synthesize a quiet vinyl/music loop after user gesture and animate record/tonearm playback.
- [ ] Cycle album accent state without leaving the room.

### Task 6: Picking and interaction behavior

**Files:**
- Create: `src/interactions/InteractionManager.js`, `src/interactions/interactionConfig.js`

**Interfaces:**
- Produces: `register({id, proxy, visual, label, action})`, `setLocked(value)`, `updatePointer(event)`, `activateAt(event)`, `screenPositionFor(id)`.

- [ ] Register invisible hit proxies for all required Type A and Type B objects.
- [ ] Implement hover cursor, stronger outline, compact hint text, and lockout during transitions.
- [ ] Wire in-room actions for lamp, record player/rack, and window scenery.
- [ ] Confirm each proxy is reachable from at least one intended fixed camera.

### Task 7: UI and complete route flow

**Files:**
- Create: `src/ui/createHud.js`, `src/ui/RouteOverlay.js`, `src/routes/routeConfig.js`
- Modify: `src/main.js`, `src/styles.css`

**Interfaces:**
- Produces DOM controls with stable `data-testid` values and hash routes for Projects, Gallery, Reading, and Movies.

- [ ] Build camera and environment controls, current-state labels, interaction legend, hover hint, and sound/lamp state feedback.
- [ ] On Type A activation, lock input, focus the camera, then open the matching route overlay.
- [ ] On close or browser Back, hide the overlay and restore the previous fixed room camera.
- [ ] Refresh each hash route and confirm it loads a working page with a return control.

### Task 8: End-to-end acceptance and visual tuning

**Files:**
- Create: `playwright.config.js`, `tests/e2e/room.spec.js`
- Modify: room/camera/style files as observations require.

**Interfaces:**
- Browser tests use `data-testid` controls and `window.__ROOM_APP__.interactions.screenPositionFor(id)` for true canvas clicks.

- [ ] Add browser assertions for initial render, three cameras, camera motion completion, all four Type A routes and return, record player, lamp, scenery, time override, resize, and direct route refresh.
- [ ] Capture page and console errors; fail the suite on either.
- [ ] Run `npm test -- --run`, `npm run build`, and `npm run test:e2e`.
- [ ] Capture and inspect overview, desk, and right-wall screenshots at 1920x1080 and overview screenshots at 2560x1440.
- [ ] Re-read every final acceptance item, fix any failure, rerun the full suite, and only then mark the goal complete.
