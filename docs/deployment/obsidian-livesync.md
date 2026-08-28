# Obsidian LiveSync production connection

The production LiveSync endpoint is the CouchDB path exposed at
`https://sync.elysiumm.top/<LIVE_PATH>/`. The value of `LIVE_PATH` is a private
deployment secret and must remain in the server environment only.

## Preservation rules

- Keep the Obsidian plugin's encrypted CouchDB connection as-is; do not replace
  it with plaintext values or regenerate it from a deployment script.
- Keep CouchDB bound to loopback and expose only the authenticated Nginx path.
- Back up `/opt/obsidian-livesync/.env` before changing a non-secret setting.
- Never commit `.env`, `mirror-settings.json`, CouchDB credentials, or encrypted
  connection payloads.

## Current diagnosis (2026-08-25)

- The active public hostname is `sync.elysiumm.top`; an old `SYNC_DOMAIN` value
  of `sync.blue-album.top` was configuration drift and is corrected on the host.
- CouchDB and the mirror service are active. Authorized `_changes`, `_revs_diff`,
  `_bulk_get`, and `_bulk_docs` traffic has returned successful status codes.
- The local vault and mirror settings have `liveSync` and encryption enabled,
  but all automatic trigger toggles are currently off. This can make a newly
  opened mobile vault appear idle even though the encrypted connection is valid.
- The server-side path is therefore verified separately from device acceptance:
  a phone/tablet must still be opened with the existing connection and checked
  by creating a harmless test note and observing it on the computer.

## Verification

Use redacted status checks only: public endpoint status, CouchDB/mirror service
state, recent authorized request status codes, and device-side note arrival. Do
not log request URLs containing the private path or any credentials.

The Bilibili archive collector and its combined backup/restore deployment
files are owned by the separate Bilibili Favorites Archive project. Elysium
only consumes the resulting mirror content through its configured article and
media roots; it does not own or delete archive records.
