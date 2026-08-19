# Collection Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Obsidian capture templates, image-only homepage cards, non-navigating entries, and cached metadata lookup.

**Architecture:** Markdown remains authoritative. The Node server normalizes frontmatter, renders new homepage modes, and stores provider responses in SQLite. QuickAdd-compatible templates are shipped as vault assets.

**Tech Stack:** Node.js, SQLite via better-sqlite3, Vite, Vitest, Obsidian QuickAdd templates.

**Spec:** `docs/superpowers/specs/2026-08-19-collection-capture-design.md`

## Global Constraints

- Never require external API credentials for local Markdown rendering.
- Never expose provider secrets to browser code.
- Empty `preview` must not fall back to body text.
- The existing `/api/articles` and article routes must remain compatible.

### Task 1: Normalize collection frontmatter

**Files:** Modify `server/article-store.js`; test `tests/article-store.test.js`.

- [ ] Add failing tests for `type`, `link`, `created_at`, and image metadata.
- [ ] Run the focused tests and verify they fail.
- [ ] Implement normalized fields with safe defaults.
- [ ] Run all tests and verify they pass.

### Task 2: Render image-only and non-link cards

**Files:** Modify `src/main.js`, `src/styles.css`; test `tests/http-app.test.js`.

- [ ] Add tests proving article JSON contains the new fields.
- [ ] Render `type: image` with the cover or first embedded image.
- [ ] Render `link: false` without article anchors.
- [ ] Build and run the browser-facing HTTP smoke test.

### Task 3: Add metadata cache and provider adapters

**Files:** Create `server/metadata-store.js`, `server/metadata-providers.js`; modify `server/http-app.js`, `server/index.js`, `package.json`; test `tests/metadata.test.js`.

- [ ] Add failing cache and normalization tests.
- [ ] Implement SQLite cache and Open Library/MusicBrainz providers plus optional TMDB/IGDB providers.
- [ ] Add `GET /api/metadata/search?type=&q=` with validation and cache-first behavior.
- [ ] Run tests without network credentials.

### Task 4: Ship capture templates

**Files:** Create `templates/quickadd/*.md`, `templates/README.md`.

- [ ] Add timestamped templates for essay, image, movie, album, book, and game.
- [ ] Document one-hotkey QuickAdd setup and folder paths.
- [ ] Validate every template contains the shared frontmatter contract.

### Task 5: Deploy and verify

- [ ] Build and test locally.
- [ ] Copy application, templates, and production dependencies to the server.
- [ ] Add metadata database path and optional provider variables to the service environment.
- [ ] Restart the service and verify homepage, image card, API, and metadata endpoint.
- [ ] Commit the completed feature.
