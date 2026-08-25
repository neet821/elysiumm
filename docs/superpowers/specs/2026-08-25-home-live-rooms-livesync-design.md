# Homepage, live access, rooms, and LiveSync design

## Goal

Complete the currently deployed Elysium migration while preserving the existing
Obsidian-backed content path and the server's LiveSync connection. The production
homepage becomes a quiet, flat content stream; live and room routes remain usable
when their expected unauthenticated states are returned; and deployment/LiveSync
configuration remains reproducible from Git without copying secrets into the repo.

## Product behavior

1. The home page uses one solid background and one continuous surface for the
   header and content. The header remains fixed and readable but does not look like
   a separate translucent panel.
2. Articles are the primary feed item: large title, large readable type, cover
   centered in the item, preview below the title/cover, and time aligned at the
   lower right.
3. Essays are deliberately compact and use less vertical space than articles.
   Records have the same visual priority as articles and essays, rather than being
   demoted to an administrative/card treatment.
4. The photo strip is inserted between feed items two and three. If fewer than
   three feed items exist, it is appended after the available content.
5. Live status and live session authorization distinguish an expected 401/403
   access result from a broken API. Public live pages render their access state
   instead of being force-redirected to login by the global Axios interceptor.
6. Room hub and room detail routes use the canonical `/rooms/*` paths. Authenticated
   room APIs retain their protection; route loading and expired-session behavior do
   not create a dead-end page.

## Preservation and deployment

- The deployed `/var/www/elysiumm` tree is pulled into a dated Git snapshot branch
  before source integration. Runtime credentials, databases, Nginx TLS material,
  and Obsidian vault data are excluded from Git.
- `main` receives the approved `Frontend From Zero` history and the implementation
  commits. The old feature branch is removed only after `main` is pushed and
  verified equal to its remote.
- Every source or deployment-template change is committed and pushed. Production
  deployment uses the committed revision marker and keeps a rollback package.
- LiveSync's encrypted connection fields are never rewritten by scripts. The stale
  server `SYNC_DOMAIN` value is corrected to the active `sync.elysiumm.top` route;
  endpoint/authentication and device-side trigger settings are verified separately.

## Non-goals

- Do not migrate or rewrite Obsidian notes, LiveSync encrypted settings, CouchDB
  data, user accounts, or room data.
- Do not expose CouchDB credentials, invite tokens, or private stream paths in Git,
  logs, screenshots, or reports.
- Do not redesign authenticated admin pages unrelated to the requested homepage,
  live, and room behavior.

## Verification

- Focused frontend tests cover flat home classes, feed ordering/placement, large
  article treatment, compact essays, record parity, live expected-401 handling,
  and canonical room navigation.
- Backend/deployment tests cover the release script's virtualenv bootstrap and
  systemd paths. Local build and relevant unit tests pass before deployment.
- Production checks cover the release marker, service status, HTTPS home/API,
  live status, room API authorization, and absence of new 5xx responses.
- LiveSync checks cover the active public endpoint, authorized CouchDB traffic,
  mirror health, and the exact remaining device-side acceptance step. A mobile
  device cannot be declared fixed without a real sync from that device.
