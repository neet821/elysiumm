# Production frontend snapshot — 2026-08-25

This directory is a byte-for-byte pull of the files served from `/var/www/elysiumm`
on the production server at 2026-08-25 23:20 +08:00. It is retained as a deployment reference,
not as the source tree for future releases.

## Provenance

- Server: `aliyun` (`8.148.83.28`)
- Web root: `/var/www/elysiumm`
- Matching source/build revision: `9fda392`
- Pulled files: 70
- Snapshot contents: `frontend/`
- Server rollback bundle: `/home/elysiumm/backups/releases/20260825T231951+0800-pre-sidebar-live-fix`

The backend source, runtime environment, databases, TLS material, Nginx files,
systemd units, and Obsidian/CouchDB credentials are intentionally outside this
snapshot. They remain managed on the server and must be backed up separately
before any deployment change.

## Verification

The following hashes were captured after the pull:

```text
0a67fd80258ca2793715f7426c63b5cb27dd1b9f0d1185904afffae91c2b964c  frontend/index.html
94d2dc2a920f830a045ff379c4b72060081efeed3c83fa75fd434b2023b59ea4  frontend/assets/index-zjQxGCVA.js
a60d31073302ca5de5e04389b546e8217e04de8f3cb9e86c3088fb4b4623e7e4  frontend/assets/index-DynSOEug.css
```
