# Obsidian Article Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a minimal browser-style homepage and reader for Markdown articles stored in the server's Obsidian `网站内容/文章` directory.

**Architecture:** A small Node.js HTTP application serves the built static frontend and exposes read-only article, media, and health endpoints. The server-side parser reads only the configured article root, extracts Frontmatter and Markdown, and the browser renders the index or reader view based on the URL.

**Tech Stack:** Node.js 20+, native HTTP APIs, `gray-matter`, `marked`, `sanitize-html`, Vite, vanilla JavaScript, CSS, Vitest, Playwright, systemd, Nginx.

**Spec:** `docs/superpowers/specs/2026-08-19-obsidian-article-home-design.md`

## Global Constraints

- The visual style is plain browser-like typography: no gradients, shadows, decorative illustrations, 3D, animation, or complex navigation.
- Articles remain on the server and are never copied into Git or the frontend bundle.
- The article root is configured explicitly on the server and all resolved paths must stay inside it.
- Preserve a rollback copy of the current public files and Nginx configuration before deployment.
- Do not claim deployment success without fresh local build, browser, HTTPS, API, article, media, and health checks.

### Task 1: Create the article parser and HTTP API

**Files:**
- Create: `package.json`
- Create: `server/article-store.js`
- Create: `server/http-app.js`
- Create: `tests/article-store.test.js`
- Create: `tests/http-app.test.js`

**Interfaces:**
- `createArticleStore({ rootDir })` returns `{ listArticles(), getArticle(slug), resolveMedia(slug, relativePath) }`.
- `createHttpApp({ articleStore, publicDir })` returns a Node HTTP request handler.
- `GET /api/articles` returns `{ articles: [...] }`.
- `GET /api/articles/:slug` returns `{ article: {...}, html: "..." }`.
- `GET /media/:slug/:path` returns the attachment bytes only when the resolved path remains within the article directory.

- [ ] **Step 1: Write failing parser and API tests** covering standard Frontmatter, title-followed YAML, excerpt fallback, date sorting, safe slug lookup, path traversal rejection, article JSON, and health response.
- [ ] **Step 2: Run `npm test -- --run` and verify the tests fail because the modules do not exist.**
- [ ] **Step 3: Add the minimal package metadata and implement Frontmatter extraction, Markdown rendering, slug mapping, safe path resolution, and HTTP responses.**
- [ ] **Step 4: Run `npm test -- --run` and verify all parser/API tests pass.**
- [ ] **Step 5: Commit with `git add package.json server tests && git commit -m "feat: add safe obsidian article api"`.**

### Task 2: Build the single-page browser-style frontend

**Files:**
- Create: `index.html`
- Create: `src/main.js`
- Create: `src/styles.css`
- Create: `vite.config.js`
- Create: `tests/frontend.spec.js`
- Modify: `package.json`

**Interfaces:**
- `/` renders the article index.
- `/article/<slug>` renders the reader and keeps a link back to `/`.
- The browser consumes `/api/articles` and `/api/articles/:slug` without embedding article content in the bundle.

- [ ] **Step 1: Write a failing Playwright test** for index title/list, a Frontmatter cover/excerpt, article navigation, reader content, back link, and narrow viewport layout.
- [ ] **Step 2: Run `npm run test:browser` and verify it fails because the frontend does not exist.**
- [ ] **Step 3: Implement the Vite entry, data loading, index/reader rendering, safe external-link behavior, loading/error states, and plain responsive CSS.**
- [ ] **Step 4: Run `npm run test:browser` against a fixture article root and verify the browser tests pass without console errors.**
- [ ] **Step 5: Run `npm run build` and commit with `git add index.html src vite.config.js package.json tests/frontend.spec.js && git commit -m "feat: build plain article home"`.**

### Task 3: Add production startup and deployment configuration

**Files:**
- Create: `server/index.js`
- Create: `deployment/elysiumm-articles.service`
- Create: `deployment/nginx-elysiumm-articles.conf`
- Create: `.env.example`
- Modify: `package.json`

**Interfaces:**
- `npm start` binds the app to `HOST` and `PORT` and reads `ARTICLE_ROOT`.
- The systemd service runs the app from its release directory with a server-only `ARTICLE_ROOT`.
- Nginx proxies the public homepage/API/media requests to the app while retaining HTTPS and the existing domain.

- [ ] **Step 1: Add a production start script and environment template.**
- [ ] **Step 2: Add systemd and Nginx templates with explicit cache and proxy behavior.**
- [ ] **Step 3: Run `npm test -- --run` and `npm run build` again after configuration changes.**
- [ ] **Step 4: Commit with `git add server/index.js deployment .env.example package.json && git commit -m "ops: add article site runtime"`.**

### Task 4: Deploy and perform public acceptance

**Files:**
- No source files; deploy the exact validated commit to the server.

**Interfaces:**
- Server article root: the actual directory containing `网站内容/文章`, discovered and verified on the host before activation.
- Public checks: `https://elysiumm.top/`, `/api/health`, `/api/articles`, one real `/article/<slug>`, and its cover/media URL.

- [ ] **Step 1: Inspect and record the actual server article directory and current public release paths.**
- [ ] **Step 2: Create a timestamped backup of current public files, service configuration, and Nginx configuration.**
- [ ] **Step 3: Copy the built release, install dependencies, configure `ARTICLE_ROOT`, install/restart the dedicated service, and validate Nginx syntax.**
- [ ] **Step 4: Run local and remote HTTP checks, then use a real browser at desktop and narrow widths to verify the index, reader, media, and console.**
- [ ] **Step 5: If every check passes, commit any deployment documentation and report the public URL; otherwise restore the recorded backup before reporting the blocker.**
