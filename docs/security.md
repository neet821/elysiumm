# Blue Album security model

## Threat model

The release assumes an untrusted browser, untrusted uploaded names and content, untrusted room payloads, untrusted device clients and potentially unavailable third-party services. It also assumes the host administrator, root-owned production environment file and database operator are trusted. The goal is to protect account data, private files, credentials, room authority and restore integrity against cross-user access, path traversal, spoofed identity, stale writes and accidental operator error.

## Authentication

Passwords are hashed with bcrypt using 12 rounds after enforcing a byte-length policy. HTTP Authentication uses signed access and refresh JWTs with distinct token types. Protected requests resolve the named user again and reject missing, invalid, unknown or inactive accounts. Socket.IO authenticates the connection and stores the server-resolved user identity; event payload user identifiers are not trusted.

`SECRET_KEY` is required. Production preflight rejects missing, short or placeholder values. It must be generated outside the repository, kept in a mode-600 environment file and rotated as a coordinated logout event. Database passwords, sync device credentials and provider cookies must never be committed or printed in release logs.

## Authorization

Authorization is enforced server-side at both route and service boundaries. Normal users may access only their own private Collection data and rooms they joined. Hosts and room members receive different controls. Administrator APIs require an active user with the administrator role; disabling an account immediately blocks new protected HTTP and Socket.IO activity.

Admin files use authenticated numeric download routes backed by private UUID storage names. Managed video and subtitle streams require room membership or a short-lived media access token. Public `/uploads` is reserved for intentionally public assets and is not the administrator/private storage root.

## CORS and browser boundary

CORS is explicit in release configuration and production preflight rejects `*`. Development may list localhost or Codespaces origins. Credentials are allowed only for configured origins. API and WebSocket endpoints should remain same-origin behind Nginx in production. External links open as ordinary navigation; secrets are never appended to them.

## Socket.IO and state integrity

The supported deployment is one backend worker. Each mutation uses the authenticated connection identity, membership and role. Playback actions carry bounded payloads and expected versions; stale versions fail with a conflict instead of overwriting current state. Reconnect obtains an authoritative snapshot.

## File upload and path safety

File upload endpoints stream to managed temporary files, enforce type and size limits, reject empty or dangerous content, verify declared sizes and hashes where applicable, and publish atomically. File names are display metadata only. Reads, deletion, backup and restore re-resolve a database path beneath the configured root and reject absolute, traversal, cross-root and tampered paths. Failed writes clean partial state or restore the previous file.

## SSRF and external URLs

SSRF controls differ by feature. The server-side audio resolver accepts only credential-free HTTP(S) URLs on the selected provider's approved host list. Kavita links are derived from one credential-free configured base plus an encoded relative reader path. External video URLs are syntax-checked and stored for the browser to load; the backend does not fetch them. Any future server-side fetcher must add DNS/IP-range validation, redirect limits, size limits and a host allowlist before release.

## Rate limiting and Audit evidence

Rate limiting protects login attempts, administrator mutations, file uploads, provider searches and real-time mutations. Current limiters are in-process, which matches the single-worker boundary. Administrator and real-time Audit rows record actor, action, resource, outcome and bounded safe detail; they deliberately omit tokens, private message content, credentials, absolute paths and exception text.

## Backup and restore security

Release and rollback bundles are mode-restricted and contain sensitive configuration. `SHA256SUMS` detects accidental change inside the trusted root-owned backup area. Rollback rejects bundles outside that root, archive traversal, checksum mismatch, missing artifacts and missing previous code revision; applying it requires an exact confirmation string and root. A second safety bundle is created before rollback mutation.

## Privacy

Public serializers omit ownership-only descriptions, credential digests, storage paths, provider cookies and internal errors. Books exposes only published entries and credential-free reader links. Public Sync returns a device secret only at creation or rotation. Room histories are bounded and filtered for the current viewer. Administrators can see operational metadata but not secrets or private content through the overview/security evidence endpoints.

Live viewing uses a short-lived HttpOnly cookie after server-side authorization. Public, signed-in allowlist and anonymous invite access share the same media gate, so revoking an invite also blocks later HLS requests. Raw stream keys and invite tokens are returned only once and stored as digests. Live visitor records contain IP address, locally resolved region, device, operating system, browser and watch duration; they are administrator-only and expire after 90 days. Region lookup does not send IP addresses to an external service. Recording routes resolve every file beneath the configured recording root and never return the absolute storage path.

The current direct-IP HTTP deployment cannot set a usable Secure cookie, so it uses `LIVE_COOKIE_SECURE=0`. This is a documented temporary transport risk: HTTPS must be enabled before treating invite links as confidential over untrusted networks, after which the setting must return to `1`.

## Known limitations

- JWT revocation is not persisted as a per-session denylist; short access lifetimes, account disabling and key rotation are the available controls.
- Rate limits, live presence and Socket.IO rooms are process-local, so multiple workers require a shared design that is not part of this release.
- Release bundles use root-owned checksums, not an external signature or immutable remote vault.
- TLS, host firewall, database grants, off-host backup replication, alerting and operating-system patching remain operator responsibilities.
- Chromium is the available real browser for local acceptance; other engines receive source/build compatibility checks until run in their own environments.
