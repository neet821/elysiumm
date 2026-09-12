# Mineradio attribution boundary

The historical standalone Mineradio browser/server integration has been
retired from Elysium. The live website does not start a Mineradio process, open
port 3000, render an iframe, or proxy `/mineradio/` routes.

The maintained Elysium implementation is split into:

- `frontend/src/features/music/`: native room player, lyrics, cover, particles
  and room controls;
- `backend/music/`: direct NetEase, QQ Music and Audius provider adapters;
- `backend/music_providers/`: an opt-in rollback/test facade for the retired
  HTTP bridge; production imports the contracts from `backend/music/`.

The remaining upstream material in this directory is retained only as a
licensing/attribution reference for the migration. It is not part of the
production release payload and must not be used as a service entrypoint.
The upstream GPL-3.0 license and visual-identity notice remain in `LICENSE`
and `NOTICE.md`.
