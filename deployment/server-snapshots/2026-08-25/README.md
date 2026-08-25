# Production frontend snapshot — 2026-08-25

This directory is a byte-for-byte pull of the files served from `/var/www/elysiumm`
on the production server at 2026-08-25. It is retained as a deployment reference,
not as the source tree for future releases.

## Provenance

- Server: `aliyun` (`8.148.83.28`)
- Web root: `/var/www/elysiumm`
- Release marker: `7fd92ad`
- Pulled files: 68
- Snapshot contents: `frontend/`

The backend source, runtime environment, databases, TLS material, Nginx files,
systemd units, and Obsidian/CouchDB credentials are intentionally outside this
snapshot. They remain managed on the server and must be backed up separately
before any deployment change.

## Verification

The following hashes were captured after the pull:

```text
ec741e1b0593735d4c9f996852297215ec50a335475272455148ed1909306e62  frontend/index.html
34053c83d459fcf2ce464901b0a5d0c73538bea676aabacf93c7fac71458c110  frontend/assets/index-D_LrUCpZ.js
517a9f864f2f344d2f250912cf61c9a7fbdca0724597a14f49c00df175e8f938  frontend/assets/index-B_npYNUJ.css
```
