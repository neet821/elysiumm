# Blue Album release checklist

Fresh closure gate: 2026-07-16 at `6556621`, `scripts/release-gate.sh`, PASS in 236 seconds on isolated local state.

## Status meanings

- **PASS** — implemented and verified by the cited current command or evidence.
- **BLOCKED** — the remaining check requires external authorization, credentials,
  infrastructure or an unavailable browser engine; local substitutes are complete.
- **FAIL** — locally actionable work is incomplete. A release candidate cannot
  contain a FAIL.

## Automated release evidence

| Area | Status | Current evidence |
| --- | --- | --- |
| Fail-closed release configuration | PASS | Gate step 1 validates secrets/placeholders, CORS, persistent roots, current runtimes, reproducible install, health gates, Socket.IO proxy, CI entrypoint and tracked-file safety. |
| Repository checks | PASS | Gate step 2 runs fatal checks, compilation, 312 backend tests, 198 frontend component tests and 6 source-contract tests. |
| Migrations | PASS | Fresh SQLite reaches `0010_repair_legacy_gaps`; legacy/downgrade and skipped-history repair tests pass. |
| Frontend production build and budget | PASS | 1,933 modules; initial JS 267,663 bytes / gzip 87,124; total JS 764,533; largest JS 267,663; CSS 180,632; 70 asynchronous chunks. |
| Backup and restore | PASS | Temporary 60-table database migrated, seeded, backed up, mutated, restored and verified; integrity `ok`, SHA-256 verified and workspace removed. |
| Accessibility and responsive layout | PASS | Chrome 150 checks 34 page/width combinations from 360 through 2560 pixels plus keyboard, focus, reduced motion and theme fallback. |
| Critical browser flows | PASS | Isolated music, video, tabletop and Books/Files/admin flows pass with no unexpected browser error, external request, private-path/secret leak or overflow. |
| Production deploy or rollback | BLOCKED | No production authority or credentials are in scope. Preflight, staging, checksummed bundle, verify-only rollback and recovery scripts are fixture-tested; no live mutation was attempted. |

## Homepage and navigation

| Target acceptance | Status | Evidence |
| --- | --- | --- |
| Hero is the only first-screen emphasis; Hello prefix hides on scroll, German line/body follow and reverse scrolling restores it | PASS | Phase 3 component and real-browser scroll acceptance. |
| No “Explore Archive” or standalone Photos top entry; messages remain on Home and Index is a normal card | PASS | Phase 3/route tests and Phase 11 desktop/mobile navigation checks. |
| Short cards do not create large gaps; images use controlled ratios; tags remain semantically distinct | PASS | Editorial-grid tests and responsive browser screenshots. |
| Administrators can configure text; dark/light Hero decorations differ | PASS | Homepage API/admin tests and theme browser checks. |
| Reduced motion remains usable | PASS | Phase 3 behavior tests and Phase 11 live reduced-motion check. |
| Desktop/mobile include Archive, Collection, Music, Books, Account and Theme; public Tools/Services are absent | PASS | Phase 2 shell tests, route contracts and Phase 11 keyboard/mobile checks. |

## Collection

| Target acceptance | Status | Evidence |
| --- | --- | --- |
| User isolation, root and nested folders, and cycle rejection | PASS | Collection service/route authorization and hierarchy tests. |
| Search and recent/most-visited views | PASS | Search-engine, ordering and browser acceptance. |
| Bulk move, copy and delete | PASS | Transactional bulk-operation tests and private workspace browser flow. |
| JSON/Netscape HTML import, dry run and bounds | PASS | Import parser/route tests for valid, duplicate and unsafe input. |
| Pre-import backup and all-or-nothing rollback | PASS | Forced-failure transaction and backup/restore tests. |
| Public output contains only `is_public` items and omits private fields | PASS | Public serialization and cross-user regression tests. |

## Player and catalog

| Target acceptance | Status | Evidence |
| --- | --- | --- |
| Standalone `PlayerAdapter` and playable deterministic test Track | PASS | Player adapter/stage tests and Phase 5 browser acceptance. |
| Core player imports no room/provider service and reads no login Cookie | PASS | Source-contract checks and browser instrumentation. |
| play/pause/seek/timeupdate/ended/error and complete cleanup | PASS | Adapter/controller lifecycle tests. |
| Original Mineradio author and GPL-3.0 information retained | PASS | Visible player attribution plus `LICENSE_NOTICE.md`, `mineradio/LICENSE` and `NOTICE.md`. |
| NetEase/QQ share canonical response; Audius/local fit the same catalog | PASS | Provider normalization and canonical persistence tests. |
| One provider failure degrades, duplicates merge/stand distinctly and provider/availability are shown | PASS | Federated-search tests and Phase 6 responsive browser flow. |
| No membership/DRM bypass; expired audio refreshes | PASS | Resolver allowlist, availability, cache/expiry and unsafe-URL tests. |
| Search rate limits and provider timeouts are bounded | PASS | Catalog route and adapter timeout tests. |

## Music rooms

| Target acceptance | Status | Evidence |
| --- | --- | --- |
| Socket connection requires valid JWT and actor comes from session | PASS | Real-time identity/security regressions. |
| Nonmembers cannot subscribe; hosts and members cannot impersonate roles | PASS | Membership/permission tests and two-client flow. |
| Snapshot restores state and stale versions are rejected with current safe state | PASS | Snapshot/service/protocol tests. |
| Reconnect/page restore resynchronize; three drift bands meet the specification | PASS | Synchronization-engine tests and Phase 7 two-client Chrome flow. |
| Queue, voting, chat, private history and multi-tab presence enforce role/privacy rules | PASS | Domain/realtime tests and critical browser flow. |
| Closing/expiring rooms cleans only owned allowed resources | PASS | Lifecycle/upload-cleanup tests. |

## Video rooms

| Target acceptance | Status | Evidence |
| --- | --- | --- |
| Independent playlist, URL/managed upload, metadata and subtitles | PASS | Video domain/API tests and Phase 8 flow. |
| Server-authoritative play/pause/seek/rate/media version with reconnect and drift correction | PASS | Shared Room Core tests and two-client browser acceptance. |
| Managed files enforce membership, paths, size/type and byte-range streaming | PASS | Upload/stream/security tests; final server drift after range fix is within 0.022 seconds. |
| Buffering is connection-scoped and ephemeral; ended advances exactly once | PASS | Real-time multi-tab/ended idempotency tests. |
| Local volume/fullscreen do not become shared authority | PASS | Player/controller tests and browser flow. |

## Games

| Target acceptance | Status | Evidence |
| --- | --- | --- |
| One deterministic game contract supports tic-tac-toe and 15×15 Gomoku | PASS | Pure definition/registry tests. |
| Public/private/password/invite rooms; players, spectators, ready/start and reconnect | PASS | Lobby/service/API tests and three-client browser flow. |
| Server validates turn, timeout, surrender, draw and version in one transaction | PASS | Unified action and rollback tests. |
| Chat/presence are identity-bound and role-filtered | PASS | Real-time security and multi-tab tests. |
| Hidden state stays viewer-specific | PASS | Dedicated hidden-information test definition across REST/realtime/replay. |
| Replay hash chain detects tampering, gaps, order and final-result mismatch | PASS | Replay service and three-role browser tests. |

## Books, Files and administration

| Target acceptance | Status | Evidence |
| --- | --- | --- |
| Public Books exposes only published metadata and has no Kavita reader-link integration | PASS | Books API/security/component/browser tests. |
| One admin console covers content, Books, users, rooms, Files, services and security; server backups are external | PASS | Admin shell/route tests and all-section browser flow. |
| Normal users cannot enter administrator routes or legacy redirects | PASS | Protected-route and API authorization tests. |
| Manual uploads reject traversal and enforce size/type, temporary write and atomic replace | PASS | Administrator file storage tests. |
| Public Sync credentials are one-time/digested/rotatable/revocable; uploads enforce digest, quota and atomicity | PASS | Device and whole/chunk upload regressions plus real browser lifecycle. |
| FRP file synchronization remains authenticated and path-safe without website service control | PASS | File-sync API and redaction tests. |
| Deployment rollback and bookmark-import safety backups retain verified recovery paths | PASS | Release script fixtures, bookmark routes and isolated recovery rehearsal. |

## Release readiness

| Target acceptance | Status | Evidence |
| --- | --- | --- |
| Locked install, checks, tests, migration, build and critical E2E run in one fail-fast command | PASS | `scripts/release-gate.sh` and static/dynamic gate tests. |
| CI reuses the same release gate | PASS | `.github/workflows/quality.yml` and release-config regression. |
| Production configuration fails closed | PASS | Placeholder/weak secret, CORS, worker, persistence, health and proxy tests. |
| Deployment makes a verified pre-migration bundle and stages frontend safely | PASS | Release-script fixture tests; live apply remains blocked. |
| Rollback verifies root/checksum/revision/confirmation and restores database/code/config/services/frontend together | PASS | Rollback fixture tests; live apply remains blocked. |
| Architecture, security, data, migration, testing, recovery and deployment docs are current and linked | PASS | Documentation/link/command regression tests. |
| Performance budget, eight-width responsive and accessibility checks | PASS | Build-budget script and Chrome 150 Phase 11 browser acceptance. |
| Final report contains scope, architecture, files, migrations, security, tests, performance, compatibility, licenses, deploy/rollback, blockers and limitations | PASS | `FINAL_REPORT.md` plus documentation regression. |

There are no current FAIL rows. BLOCKED production or external-service rows do not
hide locally actionable work and do not weaken the isolated release bundle.

## Required command

From a clean reviewed checkout with Python 3.12-compatible dependencies, Node
20-compatible dependencies and Chrome available:

```bash
scripts/release-gate.sh
```

The gate stops on the first failure and runs release configuration, full repository
checks/migrations/build/budget, recovery, Phase 11 accessibility/responsive checks,
music rooms, video rooms, tabletop, and Books/Files/administration. It does not call
production deployment, rollback, Docker startup, Nginx, systemd, FRP, DNS or a
third-party account.

## Evidence required before a real deployment

- [ ] Reviewed release commit and clean tree are recorded.
- [ ] `scripts/release-gate.sh` passes on that exact commit.
- [ ] Production environment file is host-only, mode `600`, placeholder-free and
  passes read-only preflight.
- [ ] Database/application health, disk, persistent roots and current revision are recorded.
- [ ] An off-host backup exists and the intended release-bundle destination is writable.
- [ ] Maintenance window, incident lead and rollback decision owner are named.
- [ ] Expected public, protected, administrator and real-time smoke results are written down.
- [ ] Exact rollback bundle and confirmation text are prepared but not executed.

## Abort conditions

Abort on any gate failure, dirty/unreviewed code, placeholder or overexposed secret,
wildcard production CORS, migration drift, missing backup, checksum mismatch, low
space, unexplained unhealthy service, failed Nginx validation, storage mismatch,
database integrity failure or changed authorization. Preserve logs and bundles
without secrets. Follow [deployment](deployment.md) and
[backup/restore drill](backup-restore-drill.md); do not improvise a schema downgrade.

## Honest compatibility and external boundaries

Chrome 150 is the real browser used in final local acceptance. Firefox and WebKit
have source/production-build evidence but were not executed here. Music providers
use safe unavailable states, adapters and mocks when credentials are absent. Live
production, provider accounts and Firefox/WebKit execution are BLOCKED by external
state, not reported as PASS. Kavita is an external server boundary and is not part
of website acceptance.
