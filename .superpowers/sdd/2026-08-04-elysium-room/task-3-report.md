# Task 3 Report — Desk, right wall, and personal details

## Result

Implemented the complete desk zone, right-wall record collection, and restrained room details using only local Three.js primitives and the shared outlined material system.

Implementation commit: `f8621b2`

## RED / GREEN evidence

### Initial registry and structure contract

- RED command: `npm test -- --run tests/roomFurniture.test.js`
- RED result: 3 tests failed as expected because the room only exposed `window`; the required furniture registry entries, zone groups, and animation references did not exist.
- GREEN command: `npm test -- --run tests/roomFurniture.test.js`
- GREEN result: 3/3 tests passed after adding the three room-zone modules and integrating them into `createRoom()`.

### Visual refinement contract

- RED command: `npm test -- --run tests/roomFurniture.test.js`
- RED result: 1 test failed as expected because `photo-grid-wires` did not exist and the first render used an overly heavy solid photo-board backing.
- GREEN command: `npm test -- --run tests/roomFurniture.test.js`
- GREEN result: 3/3 tests passed after replacing the solid board with a lightweight BufferGeometry wire grid.

## Implementation summary

- Desk zone: long desk, apron and legs, monitor and stand, keyboard, lamp, chair, plant, notebook, pencil cup, and monitor cable.
- Record zone: low cabinet, open cubbies, record player, record, tonearm, dust cover, album rack, records, three wall shelves, books, CDs, and shelf plant.
- Decor: floor-board seams, back-wall print, right-wall photo grid, photo cards, framed movie poster, labels, and small accent details.
- Registry: `monitor`, `lamp`, `recordPlayer`, `recordRack`, `photoWall`, `books`, `moviePoster`, and existing `window` now expose `visual`, `proxy`, and `label`; record/lamp entries also retain later controller references.
- Materials: all new furniture colors are palette-driven through the shared material registry; outlined boxes, cylinders, spheres, and BufferGeometry lines use the existing edge system.
- Disposal: proxy materials are explicitly released and all zone geometries remain covered by room disposal.

## Full verification

- `npm test -- --run`: 3 files passed, 14/14 tests passed.
- `npm run build`: passed with Vite 7.3.6, exit code 0.
- `git diff --check`: passed with no whitespace errors.
- Runtime registry/bounds check: all 8 entries had a visible object, proxy, label, and non-empty proxy bounds; scene traversal found 143 meshes and 137 line objects.

## Real browser render inspection

Used the installed Chromium headless shell with software WebGL at 1920×1080 against a temporary Vite inspection page that loaded the real `createScene()` and `createRoom()` modules. The temporary page was removed before commit.

- Overview screenshot: `/home/neet821/.codex/visualizations/2026/08/04/019fcb78-e1b6-7951-90bb-ffbe54c51c98/task3-overview-balanced.png`
- Right-wall screenshot before refinement: `/home/neet821/.codex/visualizations/2026/08/04/019fcb78-e1b6-7951-90bb-ffbe54c51c98/task3-right-wall.png`
- Right-wall screenshot after photo-grid refinement: `/home/neet821/.codex/visualizations/2026/08/04/019fcb78-e1b6-7951-90bb-ffbe54c51c98/task3-right-wall-final.png`

Observed and confirmed:

- The long desk remains the center-weighted focal point in front of the bay window.
- The cabinet, player, rack, shelves, books, poster, and photo grid create the intended denser right-side counterweight.
- All right-wall objects are legible in the orthogonal inspection view and do not materially occlude each other.
- The initial solid photo-board looked too heavy compared with the supplied image, so it was replaced with a thin wire grid and re-rendered.
- The existing default camera sits outside the right return and occludes the collection; inspection therefore used an interior overview pose consistent with the approved reference. No Task 4 camera code or production camera settings were added or changed.
- Chromium console showed Vite connection messages only; no page/runtime errors occurred.

## Self-review

- Confirmed all brief items are represented and all required registry IDs are exact.
- Confirmed visible groups and proxies are separate objects and proxy materials remain invisible.
- Confirmed no external model, texture, camera-controller, or interaction behavior was introduced.
- Confirmed the temporary visual harness is absent from the working tree.
- Confirmed changes are limited to Task 3 furniture/decor, room integration, palette-backed material definitions, and focused tests.

## Concerns

None for Task 3. Final camera framing remains intentionally owned by Task 4.

## Fix round 1 — restrained shadow cost

Implementation commit: `6f2719d`

### Review finding

The first implementation allowed 86 of 143 meshes to cast shadows. Small record labels, tonearm pieces, individual album sleeves and books, lamp stems, pots, and photo cards were paying shadow-map cost without materially improving the composition.

### RED / GREEN

- RED command: `npm test -- --run tests/roomFurniture.test.js`
- RED result: the new shadow-budget test failed against 86 casters and identified every forbidden small caster.
- GREEN command: `npm test -- --run tests/roomFurniture.test.js`
- GREEN result: 4/4 focused tests passed with 30 total casters, below the enforced maximum of 32.
- Preserved major casters include the desk top and legs, monitor screen, lamp shade, chair seat/back, cabinet shell, record-player plinth, spinning record, rack base, wall shelves, movie-poster frame, shell trim, and window frame.
- Confirmed non-casters include the lamp stem, plant pots, record label, tonearm, individual album sleeves, individual books, and photo cards.

### Verification

- `npm test -- --run`: 3 files passed, 15/15 tests passed.
- `npm run build`: passed with Vite 7.3.6, exit code 0.
- `git diff --check`: passed.
- Runtime count: shadow casters reduced from 86 to 30, a 65% reduction.
- Browser check: rendered the real scene at 1920×1080 using Chromium software WebGL. Major furniture grounding and visual hierarchy remained intact; no visible regression was found.
- Screenshot: `/home/neet821/.codex/visualizations/2026/08/04/019fcb78-e1b6-7951-90bb-ffbe54c51c98/task3-shadow-fix.png`
- The temporary browser harness was removed before commit.

### Fix-round self-review

- Change scope is limited to shadow flags and the focused regression test.
- The review's Minor notes about outline color and the unused import were intentionally not changed.
- No camera or interaction behavior was added.
