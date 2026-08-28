# Bilibili Favorites Archive Separation Design

## Goal

Make the Bilibili favourites archiver an explicitly independent project and
remove its deployment-file duplication from Elysium without interrupting the
existing production services.

## Ownership

- `/home/neet821/Desktop/Bilibili-Favorites-Archive` is the local source
  checkout for the independent archiver project.
- The Personal-Archive Git repository remains the source repository; only its
  local checkout directory and project-facing name become
  `Bilibili-Favorites-Archive` / `Bilibili Favorites Archive`.
- Elysium owns only the website and its read-only article/mirror integration.
- Archive collector deployment files and backup/restore files live under the
  archiver repository's `deploy/` directory.

## Naming and compatibility

The Python import package `personal_archive`, production user
`personal-archive`, systemd units, environment variable names, and production
paths remain unchanged in this migration. The package metadata and README use
the more specific Bilibili name, and the package exposes a new
`bilibili-favorites-archive` console entry point while retaining the existing
`personal-archive` entry point as a compatibility alias.

The following production paths are stable and must not be renamed or moved:

- `/opt/personal-archive/app`
- `/opt/personal-archive/state`
- `/opt/personal-archive/venv`
- `/opt/obsidian-livesync`
- `/etc/systemd/system/personal-archive.service`
- `/etc/systemd/system/personal-archive.timer`

## Migration sequence

1. Inventory both repositories and record the current dirty working-tree
   files; unrelated user changes are not touched.
2. Add the four missing backup/restore deployment files to the archiver
   repository and verify the existing `personal-archive.timer` is identical
   before removing the Elysium copy.
3. Move the combined-backup documentation to the archiver repository and leave
   Elysium with only its website-side integration contract.
4. Validate the archiver repository with its Python tests, lint/type checks,
   shell syntax checks, and systemd unit parsing.
5. Rename the local checkout directory only after the repository passes
   validation. No production service reads the Desktop checkout directly.
6. If production deployment is needed, stage files beside their current
   production paths, validate them, retain rollback copies, atomically replace
   only the intended file, run `systemctl daemon-reload`, and verify all
   service/timer states and website health before declaring success.

## Service-safety rules

- Do not stop or disable the active Elysium article service, LiveSync, CouchDB,
  or enabled timers for this repository separation.
- Do not use `rsync --delete` against `/opt/personal-archive` or
  `/opt/obsidian-livesync`.
- Never move an active production directory. A changed deployment file is
  installed as a validated replacement, with the previous file retained for
  rollback.
- The archive collector remains timer-triggered; `personal-archive.service`
  is not enabled directly at boot.
- Acceptance requires checking the active unit paths, executable existence,
  timer schedules, local article API health, and public website health.

## Verification

- Both repositories have the expected ownership and no duplicate
  `deployment/personal-archive` directory remains in Elysium.
- `uv run pytest`, `uv run ruff check .`, and `uv run mypy src` pass in the
  renamed archiver checkout.
- All moved shell scripts pass `bash -n`; all moved units pass
  `systemd-analyze verify` in a temporary unit directory or on the target
  host.
- Production paths and unit `ExecStart`/`WorkingDirectory` values are
  unchanged before and after the migration.
- After any production installation, `elysiumm-articles.service` and the
  enabled archive/backup timers are active or enabled as expected, and the
  article health endpoint returns success.
