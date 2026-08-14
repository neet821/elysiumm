# Blue Album 2026 final acceptance report

Date: 2026-07-16
Fresh closure-gate baseline: `6556621` (`docs: publish the final Blue Album release report`)
Target pack: `blue-album-codex-target-pack`

## Release candidate status

**Local release candidate: PASS.** Phases 0–11 are implemented. The latest complete
eight-step release gate passed in 236 seconds on isolated local state with no FAIL
item in the acceptance checklist. It ran 312 backend tests, 198 frontend component
tests, 6 frontend source-contract tests, the full migration/drift check, production
build and budgets, recovery rehearsal, accessibility/responsive checks, and the
critical multi-client browser flows.

**Production deployment or rollback: BLOCKED.** No production authorization,
credentials, approved maintenance window, off-host backup, TLS/DNS ownership or
operator was supplied. No production service, database, Nginx, FRP, systemd or
secret was read or changed. All locally controllable release, preflight, staging,
verification and rollback work is complete.

The detailed target-by-target decision record is in the
[release checklist](docs/release-checklist.md). PASS means a named current command
or isolated browser flow completed. BLOCKED is used only for external authority or
infrastructure. There is no current FAIL.

## Architecture and delivered scope

Blue Album is a React application backed by FastAPI, SQLAlchemy/Alembic and
MariaDB/MySQL. Nginx serves the built application and forwards API and Socket.IO
traffic. The supported release topology intentionally uses one backend worker;
live rooms, presence and rate limits are process-local and are not presented as a
multi-worker system.

The delivered product has these boundaries:

- Public experience: configurable Hero, writing, photography, messages, Archive,
  public Collection and Books.
- Account experience: private Collection, search engines, preferences, music and
  video rooms, games and private Files.
- Music: provider-neutral canonical catalog, legal source resolver, isolated direct
  player and server-authoritative room snapshots.
- Video: independent playlist, managed uploads, subtitles, range streaming,
  buffering telemetry and the same media-independent authoritative clock.
- Games: deterministic shared turn engine, tic-tac-toe, Gomoku, roles, chat,
  reconnect and hash-chained replay.
- Administration: one `/account/admin/*` console for overview, content, homepage,
  Books, photos, users, rooms, Files/Public Sync, server status, FRP, backups and
  bounded security evidence.
- External adapters: music providers and Kavita fail safely when credentials or
  services are absent. Provider cookies, storage paths and private secrets do not
  enter browser payloads.

The canonical system, information-architecture and music-separation decisions from
the target pack were implemented without inventing Redis, distributed workers,
background queues or production credentials. Current detail is recorded in
[architecture](docs/architecture.md), [security](docs/security.md) and
[data formats](docs/data-formats.md).

## Phase delivery summary

| Phase | Result | Delivered outcome |
| --- | --- | --- |
| Phase 0 | PASS | Target takeover, dependency/build baseline and progress ledger. |
| Phase 1 | PASS | P0 authentication, authorization, storage/restore, rate-limit, audit and migration hardening. |
| Phase 2 | PASS | Brand assets, design primitives, theme, responsive application shell and route migration. |
| Phase 3 | PASS | Configurable Hero, scroll narrative, theme-specific visuals, content grid and messages. |
| Phase 4 | PASS | Archive and isolated public/private Collection, hierarchy, search, bulk operations and transactional import/recovery. |
| Phase 5 | PASS | Standalone `PlayerAdapter`, normalized test track, direct player stage, room bridge and GPL attribution. |
| Phase 6 | PASS | Canonical music catalog, NetEase/QQ/Audius/local adapters, federated search and legal expiring-source resolution. |
| Phase 7 | PASS | Server-authoritative music Snapshot, version conflicts, reconnect/drift correction, queue, chat and history. |
| Phase 8 | PASS | Shared media Room Core and independent synchronized video domain. |
| Phase 9 | PASS | Unified tabletop contract, tic-tac-toe, Gomoku, spectators, timeouts and tamper-detecting replay. |
| Phase 10 | PASS | Books/Kavita portal, secure Public Sync, unified Files and administrator console. |
| Phase 11 | PASS | Release configuration, CI, preflight/rollback, documentation, budgets, accessibility, compatibility, recovery and release gate. |

Representative phase completion commits are `7cbee0e`, `1ce31f2`, `dea88d5`,
`3d3c4bf`, `80db6b2`, `886db84`, `6ebff7c`, `5f82b0c`, `91522bb`, `fc95026`
and `ae620ee`. The complete unit-level record remains in `AGENT_PROGRESS.md` and
`docs/progress-archive/`.

## Major file inventory

This is the review-oriented inventory; generated build output and individual tests
are intentionally not listed one by one.

- `frontend/src/design-system/`, `frontend/src/components/` and
  `frontend/src/layouts/`: brand, reusable controls, themes, loading/error boundaries
  and responsive navigation.
- `frontend/src/pages/`: public, account, room, game, Books, Files and administrator
  screens, loaded on demand through `frontend/src/App.jsx`.
- `frontend/src/features/player/` and `frontend/src/features/video/`: isolated player
  adapters/controllers and their host integrations.
- `backend/app/routers/`, `backend/app/services/` and `backend/app/realtime.py`:
  validated HTTP, domain transactions and trusted real-time identity.
- `backend/app/game_definitions/` and game services: deterministic rules, safe views
  and replay validation.
- `backend/alembic/versions/`: the linear production schema history.
- `scripts/check-all.sh`, `scripts/release-gate.sh`, browser smoke scripts,
  `scripts/rehearse-backup-restore.py`, release preflight and rollback scripts:
  reproducible local and operator checks.
- `.github/workflows/quality.yml`: locked dependency installation and the same release
  gate used locally.
- `docs/`: architecture, security, contracts, migrations, testing, recovery,
  deployment/rollback and acceptance evidence.
- `mineradio/`: preserved upstream Mineradio source, GPL-3.0 license, notice and Blue
  Album integration boundary.

## Migrations

Alembic is the production schema source of truth. The verified linear chain is:

1. `0001_legacy_baseline`
2. `0002_phase1_security`
3. `0003_phase3_homepage`
4. `0004_phase4_collection`
5. `0005_phase6_catalog`
6. `0006_phase7_music_room_authority`
7. `0007_phase8_video_room_core`
8. `0008_phase9_game_platform`
9. `0009_phase10_books_files_admin`
10. `0010_repair_legacy_gaps`

The repository gate upgrades a fresh isolated database to
`0010_repair_legacy_gaps`, checks model/head drift and covers representative
legacy upgrade and downgrade compatibility. Production deployment must create a
verified pre-migration release bundle before running `backend/run_migrations.py`.
Production recovery restores the matched database and prior code revision; it does
not guess an Alembic downgrade. See [database migrations](docs/migrations.md).

## Security

The completed P0/P1 work includes:

- required strong release secrets, signed access/refresh token types, active-user
  resolution and server-bound Socket.IO identity;
- server-side ownership, membership, host, spectator and administrator checks;
- explicit production CORS, single-worker real-time boundary and version-conflict
  rejection instead of client authority;
- bounded, allowlisted or credential-free external URLs and no provider-cookie
  exposure to the browser;
- streamed size/type-controlled uploads, managed roots, traversal rejection,
  temporary writes, digest checks, atomic publication and failure cleanup;
- one-time Public Sync credentials stored as digests, expiration/revocation,
  per-device quotas and persistent chunk-session binding;
- bounded rate limiting and audit records that exclude secrets, paths, private
  messages and internal exception detail;
- role-filtered game state and replay, checksum-verified recovery bundles and
  fail-closed release configuration.

Security regression is part of the repository and domain gates. The complete threat
model and limitations are in [security](docs/security.md).

## Verification evidence

The primary release command is:

```bash
scripts/release-gate.sh
```

Fresh closure result on 2026-07-16 at `6556621`: **PASS in 236 seconds**.

| Evidence | Result |
| --- | --- |
| Release configuration | PASS; secrets/placeholders, CORS, persistence, runtime, health, proxy and CI rules validated. |
| Backend | PASS; 312 tests plus fatal lint and byte compilation. |
| Frontend | PASS; 198 component tests, 6 source-contract tests, lint and production build. |
| Database | PASS; fresh migration to `0009`, legacy/downgrade coverage and no model/head drift. |
| Recovery | PASS; 60-table temporary database restored with integrity `ok`, verified SHA-256 and complete cleanup. |
| Accessibility/responsive | PASS; 34 page/width combinations and keyboard/focus/theme/reduced-motion checks in Chrome 150. |
| Music room | PASS; isolated two-client authority, drift, reconnect, queue/chat/history and privacy flow. |
| Video room | PASS; isolated two-client playlist/upload/stream/subtitle/rate/buffering/reconnect flow. |
| Games | PASS; isolated two-player plus spectator tic-tac-toe/Gomoku/chat/reconnect/replay flow. |
| Books/Files/admin | PASS; isolated public Books, manual/sync files, all admin sections and legacy redirects. |

The gate creates temporary state, stops on the first failure and does not call
deployment, rollback, Docker startup or privileged host commands. Full command and
interpretation details are in [testing](docs/testing.md).

## Performance and compatibility

Route-level loading removed room, game, editor and administrator pages from the
initial application bundle. The enforced production budget result is:

- initial JS: 267,663 bytes; gzip 87,124 bytes;
- total JS: 764,533 bytes;
- largest JS file: 267,663 bytes;
- total CSS: 180,632 bytes;
- asynchronous chunks: 70.

Chrome 150 executed 34 checks across widths 360, 390, 430, 768, 1024, 1366,
1920 and 2560 pixels. The checks cover landmarks/headings, names and labels, image
alternatives, keyboard focus, mobile navigation, 44-pixel menu control, reduced
motion, system theme fallback, overflow, browser errors, failed requests and
third-party traffic. Firefox and WebKit received standards-oriented source and
production-build checks but were not installed and were not claimed as live-engine
passes. Runtime Web Vitals on the actual production network remain an operator
measurement after deployment.

## Third-party licenses

The direct player preserves attribution to
[XxHuberrr/Mineradio v1.1.1](https://github.com/XxHuberrr/Mineradio) and GPL-3.0 in
`frontend/src/features/player/LICENSE_NOTICE.md`, the player interface,
`mineradio/LICENSE`, `mineradio/NOTICE.md` and `mineradio/BLUE_ALBUM_INTEGRATION.md`.
The active player uses Blue Album's browser-generated local demonstration audio and
does not embed provider credentials.

The README states that Blue Album's own code is MIT, but this repository currently
has no root `LICENSE` file. Adding a legal license text and copyright holder is an
owner decision and is recorded as a non-blocking distribution limitation rather
than silently inventing legal ownership. npm/Python dependencies and external
services remain under their own licenses and terms as represented by the tracked
lockfiles, requirements and upstream notices.

## Deployment and rollback

No live deployment was performed. For an authorized Debian/Nginx/systemd/MariaDB
single-worker release, the operator must first review the exact clean commit, create
a mode-600 `backend/prod.env`, provision TLS/database/persistent roots, name the
maintenance and rollback owners, and verify an off-host backup.

Read-only preflight:

```bash
sudo scripts/release-preflight.sh \
  --env-file backend/prod.env \
  --health-url http://127.0.0.1:8000/api/health
```

Apply only after approval:

```bash
sudo PROD_ENV_FILE="$PWD/backend/prod.env" ./start-prod.sh
```

The script makes a checksummed pre-migration bundle, records candidate and previous
revisions, runs the safe migration, stages dependencies/services/frontend, performs
an atomic frontend switch and verifies health. It does not pull or choose code.

Verify a rollback bundle without mutation:

```bash
sudo scripts/rollback-prod.sh \
  --backup-root /home/blue-album/backups \
  --bundle /home/blue-album/backups/releases/<timestamp> \
  --verify-only
```

An approved rollback requires the exact `ROLLBACK:<timestamp>` confirmation and
restores the matched database, previous code, configuration, services and frontend
after creating a second safety bundle. Exact prerequisites, abort conditions and
post-release checks are in [deployment and rollback](docs/deployment.md) and the
[backup/restore drill](docs/backup-restore-drill.md).

## External blockers

| Item | Status | Reason and completed local substitute |
| --- | --- | --- |
| Live production deploy/rollback | BLOCKED | No authorization, credentials, operator window or production infrastructure was supplied. Preflight, stage, recovery and rollback scripts are fixture-tested. |
| Live Kavita account | BLOCKED | No service/credential was supplied. Credential-free safe-link construction, unavailable behavior, mocks and browser UI are complete. |
| Live music-provider accounts | BLOCKED | No provider credentials were supplied. Adapters, normalization, timeout/failure behavior, mocks and legal resolver boundaries are complete. |
| Live Firefox/WebKit execution | BLOCKED | Engines are not installed in this workspace. Source/build compatibility passes; Chrome 150 is the recorded real engine. |

These blockers do not conceal locally actionable code or test failures.

## Known limitations

- The supported release uses one backend worker. Redis/shared Socket.IO, distributed
  presence/rate limits, background queues and horizontal scaling are future work.
- Per-session persistent JWT revocation is not present; short access lifetime,
  refresh-token handling, account disabling and coordinated key rotation are the
  current controls.
- Runtime Web Vitals, observability/alerting, TLS, firewall/database grants and
  off-host immutable backup operation depend on the real deployment environment.
- Firefox/WebKit require a future live-engine run; Chrome 150 is the only locally
  executed engine.
- International chess, Chinese chess, UNO and card games are later adapters; the
  delivered common game platform currently proves tic-tac-toe and Gomoku.
- The repository lacks a root legal license file even though the README says MIT;
  the owner should add an approved copyright/license file before redistribution.
- The frontend lint run has 43 existing non-fatal warnings. Fatal checks, tests,
  build and resource budgets pass; warning reduction is a non-blocking cleanup.

## Non-blocking follow-up enhancements

Add live Firefox/WebKit and production-network performance runs to CI infrastructure;
adopt Redis/shared real-time coordination before increasing worker count; add
external monitoring and signed/off-host release evidence; add more game definitions
through the existing contract; and resolve the root license-owner decision. None of
these changes is required to reproduce the current single-worker local release
candidate.
