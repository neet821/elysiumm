# Elysium Phase 1 Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the current Blue Album release state and create a verified, recoverable server snapshot before Elysium migration.

**Architecture:** First validate and commit only the existing Blue Album homepage work on its current `dev` branch. Then create an immutable, timestamped server snapshot outside the application repositories, separating a restricted full recovery bundle from a sanitized archive attachment.

**Tech Stack:** Git, npm, Vitest, Vite, SSH, systemd, Nginx, MariaDB logical backup, CouchDB backup tooling, tar, SHA-256.

## Global Constraints

- Do not stop or restart online services.
- Do not change DNS, certificates, Nginx, databases, CouchDB, Obsidian settings, or production application files.
- Do not commit secrets, database dumps, or private user data.
- Preserve the existing Blue Album `dev` branch and current Elysium uncommitted work.

---

### Task 1: Validate the Blue Album homepage changes

**Files:**
- Read: `/home/neet821/Desktop/Blue-Album/frontend/package.json`
- Read: `/home/neet821/Desktop/Blue-Album/frontend/src/pages/HomePage.jsx`
- Read: `/home/neet821/Desktop/Blue-Album/frontend/src/components/layout/AppShell.jsx`
- Read: `/home/neet821/Desktop/Blue-Album/frontend/tests/homepageHero.test.jsx`
- Read: `/home/neet821/Desktop/Blue-Album/frontend/tests/appShell.test.jsx`

**Interfaces:**
- Consumes the existing uncommitted `dev` worktree.
- Produces a test and build result, with no file edits.

- [ ] Inspect the exact diff and confirm it only covers the homepage, related tests, room assets, and its documentation.
- [ ] Run the frontend test command from the repository's documented package scripts.
- [ ] Run the frontend production build command.
- [ ] Record the command outputs and stop if either command fails.

### Task 2: Commit and push the validated homepage work

**Files:**
- Modify: existing changed files in `/home/neet821/Desktop/Blue-Album`

**Interfaces:**
- Consumes the validated `dev` worktree from Task 1.
- Produces one intentional Git commit on `dev` and a matching remote tip.

- [ ] Review the staged file list before staging anything.
- [ ] Stage only the current homepage implementation, its tests, assets, and documentation; do not stage environment files or unrelated changes.
- [ ] Create a commit with a message describing the 2.5D homepage preservation.
- [ ] Push `dev` to `origin` without force-pushing.
- [ ] Verify local and remote commit IDs match and record the commit ID.

### Task 3: Create a restricted server recovery snapshot

**Files:**
- Create: timestamped directory under `/home/blue-album/backups/elysium-migration-<timestamp>/`
- Create: restricted compressed recovery archive and `SHA256SUMS`

**Interfaces:**
- Consumes read-only server state from the active Blue Album deployment.
- Produces a recoverable server-side snapshot; it does not change running services.

- [ ] Capture service status, enabled state, process command lines, listening ports, mounted paths, and current Git commit.
- [ ] Archive the deployed website, application source and runtime metadata, uploaded files, recordings, service units, Nginx site configuration, live-media configuration, and backup directory manifest.
- [ ] Create a MariaDB logical backup using the existing server credentials without printing credentials or dump contents to the terminal.
- [ ] Capture CouchDB database names, document counts, replication configuration, and an application-level backup using the existing backup mechanism without exposing credentials.
- [ ] Store restricted files with owner/mode information and calculate SHA-256 checksums.
- [ ] Verify the archive can list and extract representative files into a temporary directory.

### Task 4: Produce the sanitized archive record

**Files:**
- Create: sanitized archive manifest and migration report inside the restricted snapshot directory

**Interfaces:**
- Consumes the recovery snapshot and checksum manifest from Task 3.
- Produces a concise record suitable for a private repository attachment without secrets or private data.

- [ ] Exclude database dumps, upload/media contents, private sync data, environment files, keys, cookies, and tokens from the sanitized attachment.
- [ ] Include only deployment paths, service names, versions, Git commit IDs, file counts, archive sizes, and checksum references.
- [ ] Scan the sanitized archive filenames and contents for common secret markers before finalizing it.
- [ ] Record that the original full recovery snapshot remains server-side and is not a Git attachment.

### Task 5: Final read-only verification

**Files:**
- Read: snapshot manifest, checksums, service status, Git status

**Interfaces:**
- Consumes all outputs from Tasks 1–4.
- Produces the Phase 1 handoff report.

- [ ] Confirm Blue Album `dev` is clean and matches `origin/dev`.
- [ ] Confirm Elysium's existing uncommitted changes are still present and untouched.
- [ ] Confirm all pre-existing online services remain active and no restart or stop was issued.
- [ ] Confirm the full snapshot and sanitized manifest both verify successfully.
- [ ] Write the Phase 1 handoff summary with exact paths and checksums.
