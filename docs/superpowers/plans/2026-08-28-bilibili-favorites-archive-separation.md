# Bilibili Favorites Archive Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate the Bilibili favourites backup project from Elysium, give it a specific name, and reconcile local/GitHub/server state without changing production runtime paths or deleting archived records.

**Architecture:** `Bilibili-Favorites-Archive` becomes the sole local source checkout and owns the collector plus deployment/backup files. Elysium keeps only its website and read-only mirror integration. Production compatibility identifiers and paths remain unchanged; deployment uses staged file replacement and rollback snapshots.

**Tech Stack:** Git, Python 3.12/uv, pytest, Ruff, mypy, Bash, systemd, SSH, GitHub CLI.

**Spec:** `docs/superpowers/specs/2026-08-28-bilibili-favorites-archive-separation-design.md`

## Global Constraints

- Never delete Bilibili archive notes, covers, SQLite rows, or historical metadata when a favourite disappears.
- Keep `/opt/personal-archive/app`, `/opt/personal-archive/state`, `/opt/personal-archive/venv`, `/opt/obsidian-livesync`, and existing systemd unit names unchanged.
- Never use `rsync --delete` against production application or state directories.
- Preserve unrelated dirty files in both local repositories and preserve a recoverable server snapshot before reconciliation.
- Keep `personal-archive.service` timer-triggered; do not enable it directly at boot.
- Do not restart or stop active website, LiveSync, CouchDB, or timer services for local repository separation.

### Task 1: Capture and verify the current production/local baseline

**Files:**
- Create outside repositories: timestamped local and server rollout snapshots containing Git diffs, untracked-file manifests, service paths, and checksums.

- [ ] **Step 1: Record local repository states and create recoverable diff snapshots**

Run the status, HEAD, remote, binary diff, and untracked-file inventory commands for Elysium and Personal Archive. Store the snapshots outside both working trees so they cannot become accidental Git content.

- [ ] **Step 2: Snapshot the server Personal Archive working tree before any comparison or deployment**

Create a mode-700 server rollout-backup directory containing the server Git diff, untracked-file tar, HEAD/remotes, active unit paths, and checksums. Do not read or copy secret environment files.

- [ ] **Step 3: Recheck live services and health endpoints**

Confirm the article API, backend API, public website, backup timer, archive timer, and required executable paths. Record any pre-existing Bilibili HTTP 412 failure separately from directory-separation status.

### Task 2: Reconcile the independent project source without overwriting production

**Files:**
- Modify: `/home/neet821/Desktop/Bilibili-Favorites-Archive` repository only after the baseline snapshot.
- Modify: server only through staged, validated files if a deployment correction is required.

- [ ] **Step 1: Compare local unpushed work, GitHub refs, and server dirty changes**

Use the common base `383d854`, the GitHub feature ref `codex/bilibili-resource-layout`, local commit `ec20b1f`, and the server snapshot to classify changes as already published, local-only, server-only, or conflicting.

- [ ] **Step 2: Run the Personal Archive test, lint, and type checks before committing local changes**

Run `uv run pytest`, `uv run ruff check .`, and `uv run mypy src` in the current checkout. Fix only failures caused by the scoped rename/separation work; do not rewrite unrelated user changes.

- [ ] **Step 3: Commit and push only the reconciled Personal Archive changes**

Create a focused commit on the existing feature branch for verified project changes, push it to the matching GitHub branch, and verify the remote commit hash. Do not push server-only changes until they have been reviewed against the local source.

### Task 3: Move deployment ownership into the independent project

**Files:**
- Create: `/home/neet821/Desktop/Bilibili-Favorites-Archive/deploy/backup.sh`
- Create: `/home/neet821/Desktop/Bilibili-Favorites-Archive/deploy/verify-restore.sh`
- Create: `/home/neet821/Desktop/Bilibili-Favorites-Archive/deploy/obsidian-livesync-backup.service`
- Create: `/home/neet821/Desktop/Bilibili-Favorites-Archive/deploy/obsidian-livesync-backup.timer`
- Modify: `/home/neet821/Desktop/Bilibili-Favorites-Archive/docs/operations.md`
- Modify: `/home/neet821/Desktop/elysiumm/docs/deployment/obsidian-livesync.md`
- Delete after checksum verification: `/home/neet821/Desktop/elysiumm/deployment/personal-archive/`

- [ ] **Step 1: Add the backup and restore files to Personal Archive**

Copy the already-installed production-equivalent files into the Personal Archive `deploy/` directory, preserving executable behavior and `/opt/obsidian-livesync`/`/opt/personal-archive` runtime paths.

- [ ] **Step 2: Verify duplicate and production checksums before removing Elysium copies**

Compare every moved file with the Elysium copy and the installed production file where applicable. Run `bash -n` on both scripts and `systemd-analyze verify` using temporary unit files or the server, without stopping services.

- [ ] **Step 3: Move backup documentation to Personal Archive and narrow Elysium documentation**

Keep backup schedules, retention, restore verification, and archive preservation rules in Personal Archive operations documentation. Leave Elysium documentation describing only its article/mirror dependency and health contract.

- [ ] **Step 4: Remove only the verified Elysium duplicate directory**

Delete the five untracked Elysium deployment files only after the destination files and documentation are present and all checksums/validation results are recorded.

### Task 4: Apply the specific project name with compatibility aliases

**Files:**
- Modify: `/home/neet821/Desktop/Bilibili-Favorites-Archive/README.md`
- Modify: `/home/neet821/Desktop/Bilibili-Favorites-Archive/pyproject.toml`
- Rename directory: `/home/neet821/Desktop/Personal-Archive` to `/home/neet821/Desktop/Bilibili-Favorites-Archive`

- [ ] **Step 1: Add metadata coverage for the new display name and CLI alias**

Add a focused metadata test proving the package exposes `bilibili-favorites-archive` and retains `personal-archive` as a compatibility entry point.

- [ ] **Step 2: Update project-facing name without renaming Python imports or production identifiers**

Set the distribution/display name to `bilibili-favorites-archive`, update README headings and descriptions to “Bilibili Favorites Archive”, and retain the `personal_archive` import package plus the old CLI alias.

- [ ] **Step 3: Run the full Personal Archive validation suite**

Run `uv run pytest`, `uv run ruff check .`, and `uv run mypy src` from the renamed checkout before any GitHub repository rename.

- [ ] **Step 4: Rename only the local source checkout**

Rename the Desktop directory after validation. Do not rename `/opt/personal-archive` or any systemd path. Re-run the project commands from the new directory and verify Git remotes still point to the intended repository.

### Task 5: Final repository and production acceptance

**Files:**
- Modify only the GitHub repository metadata and remote URL if the repository rename is explicitly supported and verified.

- [ ] **Step 1: Verify GitHub branch and repository state**

Confirm `main` and the feature branch hashes, pushed local commit, repository privacy, and default branch through `gh repo view` and `git ls-remote`.

- [ ] **Step 2: Rename the GitHub repository only after the source is clean and pushed**

Rename `neet821/Personal-Archive` to `neet821/Bilibili-Favorites-Archive` only after the local source is validated and the server snapshot exists. Update remotes and verify GitHub redirects/refs; do not alter production until this succeeds.

- [ ] **Step 3: Revalidate production without a directory move**

Check systemd unit `ExecStart`/`WorkingDirectory`, executable existence, timer schedules, article API, backend API, public website, CouchDB health, and the archive-preservation query. Report the existing Bilibili HTTP 412 separately if it remains.

- [ ] **Step 4: Record rollback locations and final Git status**

Report the local/server snapshot paths, the final GitHub hashes, unchanged production paths, and any unresolved pre-existing service issue. Do not claim completion unless every verification command exits successfully.
