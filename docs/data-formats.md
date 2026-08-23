# Data formats and public contracts

## General HTTP and JSON rules

The API uses UTF-8 JSON for structured bodies and `multipart/form-data` for uploads. There is no universal response envelope: each route has an explicit Pydantic response shape. Unknown fields, invalid identifiers, unsafe URLs and values outside documented bounds are rejected rather than truncated silently.

HTTP status behavior is consistent: `200/201/204` for success, `400` for an invalid domain operation, `401` for missing or invalid credentials, `403` for an authenticated user without permission, `404` for a resource hidden or absent in that user's scope, `409` for a Version conflict, `413` for size limits, `415` for unsupported media, `422` for schema validation, `429` for a limit with `Retry-After`, and `503` during maintenance or an unavailable required dependency.

## Pagination and ordering

Pagination uses bounded `skip`/`limit` or route-specific `page` values. Responses with lists define stable database or display ordering; clients must not assume insertion order where a position/display field exists. Archive, history, event, replay and security evidence routes enforce server-side maximums. A client should retain its current view when a later page fails.

## Version conflict contract

Mutable rooms, playback state, books, lists and games use integer revisions or versions. A client sends the last version it observed. The server changes state and increments the relevant version exactly once in the same transaction. A stale request returns `409` and, where the route supports it, the latest safe state so the client can recover. Retrying an old action without reconciling is not valid.

## Snapshot format

A media Snapshot carries the selected media identity, play/pause state, position, playback rate, server-time anchor and playback version. Music keeps its compatible `track_id`; video uses its playlist item identity through the shared Room Core. The server timestamp lets clients estimate current position. Clients apply small/medium/large drift correction and fetch a fresh Snapshot after reconnect, page restore or conflict.

Snapshot messages never contain provider cookies, managed storage paths or another user's private data. Buffering, local volume and fullscreen are transient client concerns and are not persisted into the authoritative playback snapshot.

## Public Sync protocol

An administrator creates or rotates a device and receives the opaque device credential once. Device requests send it as `X-Sync-Token`. The database stores only a digest and hint. Paths are normalized relative paths under that device root.

Whole-file upload includes path, declared size and SHA-256. Chunk upload also binds upload id, total size, total digest, chunk index and chunk count. Repeated identical chunks and a repeated completed identity are idempotent; conflicting metadata or content fails. The server assembles into temporary storage, verifies size/digest/quota, atomically replaces the destination and then records the event.

## Import and export

Collection Import and export supports JSON and Netscape bookmark HTML. JSON preserves folder hierarchy, bookmark metadata, tags and selected public/display fields. Imports have a dry-run mode, bounded input, duplicate handling and cycle/missing-parent validation. A real import creates a safety backup and applies one transaction; insertion failure rolls the transaction back.

HTML export uses the browser bookmark interchange structure. HTML import treats titles and URLs as untrusted text, preserves nested folders where valid and does not import script URLs. Neither format contains login tokens, storage paths or server configuration.

## Books and reader links

Public Books JSON includes published metadata, safe cover references, lists and an optional `reader_url`. Internal `reader_path`, draft state and revision stay on administrator responses. `reader_url` exists only when a credential-free Kavita base and safe relative path can be combined; it never embeds a Kavita cookie or API key.

## Game replay

Game state and action JSON is canonicalized with strict type and size limits. Each replay frame links the previous hash, version, action and resulting state hash. Reads verify the chain, current state and result before returning role-filtered frames. Legacy rooms may expose a current-state checkpoint but do not invent missing moves.

## Backup artifacts

Database backups are `.sql` for MySQL/MariaDB and `.sqlite3` for isolated SQLite drills. A release directory also contains `frontend.tar.gz`, prior runtime configuration, service configuration when present, `candidate-revision.txt`, `previous-revision.txt` and `SHA256SUMS`. These Backup artifacts are sensitive because configuration archives may contain secrets; they require restricted ownership and must not be served over HTTP.

Restore never accepts a database file as its own source, a path outside its managed backup root or an archive with absolute/traversal/link entries. See [deployment](./deployment.md) for operator steps.
