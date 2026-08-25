# Admin Console and Role-Aware Account Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route account actions by role and replace the oversized administrator console shell with a compact responsive workspace.

**Architecture:** Keep `/admin/*` and `/account` routes and existing backend APIs unchanged. Make `Header` role-aware, let `AppShell` remove public chrome for administrator routes, and make `AdminShell` the only layout owner for its pages. Reuse existing admin page modules and CSS tokens while replacing the current tab strip with a desktop rail/mobile header.

**Tech Stack:** React, React Router, lucide-react, Vitest, Testing Library, Vite, existing CSS in `frontend/src/index.css`.

**Spec:** `docs/superpowers/specs/2026-08-25-admin-console-redesign-design.md`

## Global Constraints

- Preserve `/admin/*`, `/account`, existing API endpoints, authentication guards, backend services, Obsidian files, and LiveSync services.
- Administrators target `/admin`; ordinary authenticated users target `/account`; unauthenticated users target `/login`.
- Administrator pages use a white, compact, responsive shell with a desktop left rail and mobile compact navigation.
- Verify with focused tests, lint, production build, and production DOM/API checks before claiming completion.

---

### Task 1: Lock role-aware account routing and administrator shell boundaries

**Files:**
- Modify: `frontend/src/components/Header.jsx`
- Modify: `frontend/src/components/layout/AppShell.jsx`
- Test: `frontend/tests/appShell.test.jsx`

**Interfaces:**
- Consumes: `useAuth()` fields `isAdmin`, `isAuthenticated`, and `user`.
- Produces: account links targeting `/admin`, `/account`, or `/login`; `/admin/*` pages without public `banner` or `contentinfo`.

- [ ] **Step 1: Write the failing tests**

Add assertions that an administrator's account link points to `/admin`, a normal authenticated user's link points to `/account`, a signed-out user's link points to `/login`, and the `/admin` shell has no public banner/footer.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `npm run test:unit -- --run tests/appShell.test.jsx`

Expected: FAIL because the current authenticated account target does not distinguish administrators and `AppShell` still renders the public header/footer on `/admin`.

- [ ] **Step 3: Implement the smallest routing change**

In `Header.jsx`, compute `accountTarget` as `isAdmin ? '/admin' : isAuthenticated ? '/account' : '/login'`. In `AppShell.jsx`, add an `isAdminRoute` flag for `/admin` and descendants, exclude it from `showHeader` and `showFooter`, and leave the existing `ProtectedRoute` in `routes.jsx` unchanged.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `npm run test:unit -- --run tests/appShell.test.jsx`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Header.jsx frontend/src/components/layout/AppShell.jsx frontend/tests/appShell.test.jsx
git commit -m "route account entry by user role"
```

### Task 2: Replace the administrator shell with a responsive rail

**Files:**
- Modify: `frontend/src/components/admin/AdminShell.jsx`
- Modify: `frontend/src/index.css`
- Test: `frontend/tests/adminShell.test.jsx`

**Interfaces:**
- Consumes: the existing `navigation` entries, React Router `NavLink`, and nested `Outlet`.
- Produces: one `navigation` named `管理控制台导航`, a desktop `.admin-shell__rail`, mobile `.admin-shell__mobile-header`, and a nested `.admin-shell__content` region.

- [ ] **Step 1: Write the failing shell tests**

Update the shell test to render `/admin/files` and assert the new navigation name, links `/admin` through `/admin/services`, active state on 文件, a 返回首页 link, and the nested page heading. Assert the old tab-navigation label is absent.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `npm run test:unit -- --run tests/adminShell.test.jsx`

Expected: FAIL because the current component renders the old horizontal `管理控制台页签` structure.

- [ ] **Step 3: Implement the new shell markup**

Use a two-column `.admin-shell` with a rail containing brand/back-home/navigation and a content wrapper containing the `Outlet`. Add a mobile header with a menu button, `aria-expanded`, and the same navigation links. Use `NavLink` active classes; do not add new routes or API calls.

- [ ] **Step 4: Replace the old shell CSS**

Add final overrides for `.admin-shell`, `.admin-shell__rail`, `.admin-shell__mobile-header`, `.admin-shell__navigation`, `.admin-shell__link`, and `.admin-shell__content`. Set the desktop shell to `grid-template-columns: 15rem minmax(0, 1fr)`, `max-width: 76rem`, `padding: 2rem clamp(1rem, 4vw, 3rem) 4rem`, and no top offset reserved for the public header. At `max-width: 900px`, collapse to one column and make navigation horizontally scrollable; at `max-width: 640px`, stack content and keep controls touch-sized.

- [ ] **Step 5: Run the focused test to verify it passes**

Run: `npm run test:unit -- --run tests/adminShell.test.jsx`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/admin/AdminShell.jsx frontend/src/index.css frontend/tests/adminShell.test.jsx
git commit -m "redesign responsive administrator shell"
```

### Task 3: Refresh the administrator overview surface

**Files:**
- Modify: `frontend/src/pages/AdminOverviewPage.jsx`
- Modify: `frontend/src/index.css`
- Test: `frontend/tests/adminDashboard.test.jsx`

**Interfaces:**
- Consumes: `API_ENDPOINTS.ADMIN_OVERVIEW` and `API_ENDPOINTS.MUSIC_PROVIDER_STATUS` responses already used by the page.
- Produces: accessible overview heading, refresh action, health strip, and operational navigation cards using React Router-safe links.

- [ ] **Step 1: Write the failing overview assertions**

Assert the new heading `控制台总览`, the health strip, six operational card labels, and links to `/admin/users`, `/admin/rooms`, `/admin/files`, `/admin/services`, `/admin/music`, and `/admin/live`.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `npm run test:unit -- --run tests/adminDashboard.test.jsx`

Expected: FAIL because the current overview uses `今天的 Elysium` and plain anchors without the new surface structure.

- [ ] **Step 3: Implement the overview surface**

Keep the existing API loading/error behavior, render a compact heading and refresh button, normalize missing response fields to `0`/`未知`, use `Link` for internal navigation, and add a health strip showing database and service state without exposing private fields.

- [ ] **Step 4: Add overview layout rules**

Style the heading, health strip, and card grid to fit the new rail content column. Use `repeat(3, minmax(0, 1fr))` on wide screens, two columns below 900px, and one column below 640px.

- [ ] **Step 5: Run the focused test to verify it passes**

Run: `npm run test:unit -- --run tests/adminDashboard.test.jsx`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AdminOverviewPage.jsx frontend/src/index.css frontend/tests/adminDashboard.test.jsx
git commit -m "refresh administrator overview workspace"
```

### Task 4: Verify the integrated release and deploy safely

**Files:**
- Verify: `frontend/src/components/Header.jsx`, `frontend/src/components/layout/AppShell.jsx`, `frontend/src/components/admin/AdminShell.jsx`, `frontend/src/pages/AdminOverviewPage.jsx`, `frontend/src/index.css`

**Interfaces:**
- Consumes: the completed role routing, shell, overview, and test changes.
- Produces: a pushed `main` commit, a recoverable production frontend backup, and verified public/admin route behavior.

- [ ] **Step 1: Run focused regression tests**

Run: `npm run test:unit -- --run tests/appShell.test.jsx tests/adminShell.test.jsx tests/adminDashboard.test.jsx tests/livePage.test.jsx`

Expected: all selected files pass.

- [ ] **Step 2: Run lint, build, and diff checks**

Run: `git diff --check && npm run lint && npm run build` from `frontend/` as appropriate.

Expected: no errors and a successful `frontend/dist` build.

- [ ] **Step 3: Commit and push the integrated implementation**

```bash
git add frontend/src frontend/tests
git commit -m "make administrator console role aware and responsive"
git push origin main
```

- [ ] **Step 4: Back up and publish the built frontend**

Create `/home/elysiumm/backups/releases/<timestamp>/frontend-previous` on the server, stage the built `frontend/dist`, atomically promote it to `/var/www/elysiumm`, and update both release markers to the pushed commit. Do not restart backend, Nginx, MediaMTX, Mineradio, or LiveSync services.

- [ ] **Step 5: Verify production**

Check `/api/health` is HTTP 200, `/api/live/status` is HTTP 200, all existing services remain active, and the public home/live pages render. With an authenticated administrator session, verify the avatar targets `/admin`, `/admin` has the new navigation and no public banner/footer, and `/account` remains the normal-user destination.
