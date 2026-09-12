# Deployment migration

The active deployment contract is documented in
[`docs/deployment.md`](../deployment.md). This page records the migration
boundary for the older checkout-based launcher.

The target root is `/srv/services/elysium` with independent immutable
`backend-releases/` and `frontend-releases/`, `backend-current` and
`frontend-current`, a permanently retained `baseline/`, atomically persisted
`deployment-history/`, and mutable data below `shared/`. `data -> shared` is
kept only as an explicitly tracked compatibility link until every consumer is
converted; it is never removed automatically.

The migration order is:

1. audit the real systemd, Nginx, environment, database, uploads and Articles
   mirror paths;
2. create and verify the self-contained baseline, including a restore drill;
3. initialize the release layout without switching live links;
4. install the reviewed commit into the bare Git repository and perform a
   staged deployment;
5. record two successful releases with no legacy-path access before proposing
   compatibility-link retirement.

Production migration analysis must use the backend systemd environment. It
compares the database's actual Alembic revisions with the target release graph;
only pending descendants cause a backup and `alembic upgrade heads`. Unknown,
divergent or ahead states abort without switching the backend link.

No migration step controls FlClash/FlClashCore or restarts unaffected MediaMTX.
