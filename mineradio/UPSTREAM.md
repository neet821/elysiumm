# Mineradio room frontend

The static player under `public/` is pinned to Mineradio upstream 2.1.0,
commit `89c0d230c3f1f792e5d9639781ebbf724c4efbfe`.

Elysium keeps the upstream GPL-3.0-only license and attribution files. The
only Elysium-specific frontend layer is `public/blue-album-room-bridge.js`:
it hides standalone account/catalog/update/queue entry points and connects the
room drawer to Elysium's authoritative queue and playback protocol.
