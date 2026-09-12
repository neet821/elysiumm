# Elysium CI/CD release operations

This repository-side workflow has two separate responsibilities:

- `quality` installs the locked development dependencies, resolves
  `deployment/release-impact.yml`, runs the relevant backend focused/full
  checks, runs the frontend check/budget/build, and stores the built frontend
  artifact with non-secret release metadata.
- `deployment` is production-only. It can run only for a successful `push` to
  `main`, when the `PRODUCTION_DEPLOY_ENABLED` variable is exactly `true` and
  the protected `production` environment grants its required approval.

Pull requests and pushes to other branches therefore run quality checks only.
Leaving the enable variable unset or false is the safe repository default. This
workflow does not change FlClash or FlClashCore.

## GitHub configuration

Create the following in the repository or the protected `production`
environment. Keep production values scoped to that environment where possible.

| Type | Name | Required value or purpose |
| --- | --- | --- |
| Secret | `PRODUCTION_SSH_PRIVATE_KEY` | A dedicated deploy key accepted by the production account. The workflow writes it to a mode-600 temporary file and never prints it. |
| Secret | `PRODUCTION_SSH_KNOWN_HOSTS` | Pinned `known_hosts` line(s) for the production SSH host. The workflow requires strict host-key checking and does not call `ssh-keyscan`. |
| Variable | `PRODUCTION_SSH_HOST` | DNS name or address of the production SSH endpoint. |
| Variable | `PRODUCTION_SSH_USER` | SSH account with non-interactive `sudo -n` permission for the release layout and deployment commands. |
| Variable | `PRODUCTION_ROOT` | Release root; use `/srv/services/elysium` unless the separately reviewed server layout uses another path. |
| Variable | `PRODUCTION_BASELINE_ID` | Verified directory name below `${PRODUCTION_ROOT}/baseline/`. |
| Variable | `PRODUCTION_GIT_ORIGIN` | Repository origin URL recorded by `install-release-layout.sh`. |
| Variable | `PRODUCTION_DEPLOY_ENABLED` | Must remain unset or `false` until baseline, staging, rollback, and operator checks are accepted; set to exactly `true` to enable the path. |

Configure the `production` environment with required reviewers or an equivalent
approval rule. The environment approval is an additional human gate; it is not
replaced by the repository variable. Do not put database credentials,
application secrets, or private environment-file contents in GitHub variables,
artifacts, workflow arguments, or deployment transaction metadata.

## Quality and impact selection

The quality job uses Python 3.12, Node 20, `backend/requirements-dev.txt`, and
`frontend/package-lock.json`. It checks the push/PR range with:

```text
python scripts/resolve-release-impact.py --base <base> --head <head>
```

The resulting `release-impact.json` is uploaded with the artifact. Matching
paths select component validation from the versioned impact map; unmatched
paths retain the map's full-validation behavior. Backend-impacting changes run
release-focused tests and the complete backend lint, compile, unittest,
migration, and schema checks. Frontend-impacting changes run:

```text
npm --prefix frontend run check
npm --prefix frontend run check:budget
npm --prefix frontend run build
```

The independent `quality.yml` workflow remains the full release gate. The
`deploy.yml` quality job uses the impact map for selective checks and only
uploads a frontend artifact when frontend validation is selected.

The artifact named `elysium-<commit>` contains `frontend/dist` when selected,
`frontend-budget.json`, `release-impact.json`, and SHA-256 metadata. It does
not contain `.venv`, production environment files, or credentials.

## Baseline prerequisite

Automatic production deployment is not a baseline creation mechanism. Before
setting `PRODUCTION_DEPLOY_ENABLED=true`, provision the host and create a
self-contained baseline at:

```text
/srv/services/elysium/baseline/<baseline-id>/
```

The baseline must contain a verified `BASELINE.json`, `SHA256SUMS`, runtime and
database copies, and the generated restore scripts. Its manifest must declare
self-contained runtime and database state. It must not depend on an original
release checkout or contain symlinks back to one. Shared uploads and Articles
content remain external inputs and must be listed as such in the baseline
manifest. Keep the production environment file outside Git, root-owned and
mode 600 or stricter.

Verify the exact baseline before enabling the gate:

```bash
sudo python3 scripts/verify-baseline.py \
  --baseline /srv/services/elysium/baseline/<baseline-id>
```

Also verify the required Python/Node/systemd/Nginx/runtime packages, writable
shared roots, database reachability, current application health, and enough
backup capacity. Run a staged deployment and rollback rehearsal against an
isolated copy first. The baseline ID is checked again by the workflow before
the release CLI is invoked.

## Deployment sequence

The deployment job downloads only the quality artifact and checks out the exact
commit. It transfers a temporary deployment payload over SSH using pinned host
keys, then on the server:

1. runs `scripts/install-release-layout.sh --root <root> --origin <origin>`;
2. fetches the exact commit into the bare `repository.git` without creating a
   mutable checkout;
3. verifies `baseline/<baseline-id>` without changing its contents when a
   backend release is selected;
4. installs the versioned impact map into the release root;
5. invokes `scripts/deploy-production.py` with the commit, GitHub run ID,
   unique deployment ID, bare repository, frontend dist artifact, budget/hash
   metadata, and each changed path;
6. removes the temporary payload and records the deployment transaction under
   `<root>/deployment-history/`.

The release CLI chooses frontend/backend/infra scope from the impact map. A
frontend-only release supplies the CI-built dist and does not create or inspect
the backend virtual environment or database state. A backend-only release
prepares the backend release and does not switch the frontend current link.
Database backup and migration remain conditional on the target backend's
Alembic state. Secrets are not sent as command arguments and are not printed by
the workflow.

## Rollback

Every deployment transaction records the prior component links and the
deployment ID. For an isolated component rollback, review the transaction and
run the exact confirmation form on the server:

```bash
sudo python3 scripts/rollback-production.py \
  --root /srv/services/elysium \
  --deployment-id <deployment-id> \
  --component frontend \
  --confirm 'ROLLBACK:<deployment-id>:frontend'
```

Use `--component backend` for a backend-only rollback. This creates a new
rollback transaction and changes only the selected immutable current link; it
does not guess a database downgrade. If a migration or shared infrastructure
change is involved, stop and use the reviewed baseline restore procedure (or
the full production rollback runbook) with database-owner approval, a preserved
failed state, and a fresh safety backup. Verify the baseline or release bundle
checksums before restoring, then re-check backend health, public routes,
Socket.IO, Nginx/systemd state, and the expected data/storage paths.

Do not treat a successful SSH command, a single HTTP 200, or a recorded
transaction as complete user acceptance. Record the commit, run ID, deployment
ID, selected components, health evidence, rollback target, and any unrun
browser/device or production checks separately.
