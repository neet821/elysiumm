#!/usr/bin/env python3
"""Deploy one impact-map-selected Elysium release on a server."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deployment.production_deploy import (  # noqa: E402
    DeploymentOptions,
    ProductionDeployError,
    deploy,
)
from deployment.release_impact import (  # noqa: E402
    ImpactMapError,
    changed_paths_from_git,
    resolve_impact,
    resolve_impact_json,
)


def _path(value: str) -> Path:
    return Path(value).expanduser()


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy Elysium using immutable component releases")
    parser.add_argument("--root", type=_path, default=Path("/srv/services/elysium"))
    parser.add_argument("--commit", required=True)
    parser.add_argument("--git-ref", default="refs/heads/main")
    parser.add_argument(
        "--impact-map",
        type=_path,
        help="explicit versioned impact map; defaults to <root>/deployment/release-impact.yml",
    )
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--trigger", default="github-actions")
    parser.add_argument("--github-run-id", default="")
    parser.add_argument("--path", dest="paths", action="append", default=[])
    parser.add_argument("--base-commit")
    parser.add_argument("--backend-source", type=_path)
    parser.add_argument("--frontend-source", type=_path)
    parser.add_argument("--frontend-dist", type=_path)
    parser.add_argument("--repository", type=_path)
    parser.add_argument("--backend-env-file", type=_path, default=Path("/etc/elysium/backend.env"))
    parser.add_argument("--python", dest="python_executable", type=_path, default=Path("/usr/bin/python3"))
    parser.add_argument(
        "--nginx-source",
        action="append",
        default=[],
        metavar="PATH|TARGET=PATH",
        help="candidate Nginx config, optionally with an explicit target",
    )
    parser.add_argument("--systemd-source", action="append", default=[], metavar="UNIT=PATH")
    parser.add_argument("--nginx-target", type=_path, default=Path("/etc/nginx/sites-available/elysiumm"))
    parser.add_argument(
        "--remove-nginx-target",
        action="append",
        default=[],
        type=_path,
        help="remove an explicitly mapped Nginx site file for a deleted source",
    )
    parser.add_argument("--systemd-target-dir", type=_path, default=Path("/etc/systemd/system"))
    parser.add_argument(
        "--remove-systemd-unit",
        action="append",
        default=[],
        help="remove an explicitly mapped systemd service/timer for a deleted source",
    )
    parser.add_argument(
        "--mediamtx-config-source",
        type=_path,
        help="replace the managed /etc/elysium/mediamtx.yml config",
    )
    parser.add_argument(
        "--health-guard-source",
        type=_path,
        help="replace the managed /usr/local/sbin/elysium-health-guard script",
    )
    parser.add_argument(
        "--defer-health-guard-restart",
        action="store_true",
        help="leave the health guard stopped for a controlled maintenance window",
    )
    parser.add_argument("--backend-service", default="elysiumm-backend.service")
    parser.add_argument("--health-url", default="http://127.0.0.1:8000/api/health")
    parser.add_argument("--node-version", default="CI")
    parser.add_argument("--frontend-package-lock-sha256", default="")
    parser.add_argument("--frontend-api-schema-sha256", default="")
    parser.add_argument("--backend-api-schema-sha256", default="")
    parser.add_argument("--compatible-backend-api", default="*")
    parser.add_argument("--compatible-frontend-api", default="*")
    parser.add_argument("--budget-json", type=_path)
    parser.add_argument("--skip-health", action="store_true", help="only for disposable local rehearsals")
    parser.add_argument("--print-impact", action="store_true", help="resolve impact and exit without mutating releases")
    args = parser.parse_args()

    root = args.root.resolve()
    paths = list(args.paths)
    try:
        if args.base_commit:
            paths.extend(changed_paths_from_git(root, args.base_commit, args.commit))
        if not paths:
            raise ImpactMapError("at least one --path or --base-commit is required")
        impact_map = (args.impact_map or root / "deployment/release-impact.yml").resolve()
        impact = resolve_impact(paths, impact_map=impact_map, root=root)
        if args.print_impact:
            print(resolve_impact_json(impact), end="")
            return 0
        systemd_sources: dict[str, Path] = {}
        for item in args.systemd_source:
            if "=" not in item:
                raise ValueError("--systemd-source must use UNIT=PATH")
            unit, source = item.split("=", 1)
            if not unit or not source:
                raise ValueError("--systemd-source must use UNIT=PATH")
            systemd_sources[unit] = _path(source).resolve()
        nginx_source: Path | None = None
        nginx_sources: dict[Path, Path] = {}
        for item in args.nginx_source:
            if "=" not in item:
                if nginx_source is not None:
                    raise ValueError("plain --nginx-source may be provided only once; use TARGET=PATH for additional configs")
                nginx_source = _path(item).resolve()
                continue
            target, source = item.split("=", 1)
            if not target or not source:
                raise ValueError("--nginx-source must use PATH or TARGET=PATH")
            nginx_sources[_path(target).resolve()] = _path(source).resolve()
        budget = None
        if args.budget_json:
            budget = json.loads(args.budget_json.read_text(encoding="utf-8"))
            if not isinstance(budget, dict):
                raise ValueError("--budget-json must contain an object")
        transaction = deploy(
            DeploymentOptions(
                root=root,
                commit=args.commit,
                git_ref=args.git_ref,
                deployment_id=args.deployment_id,
                trigger=args.trigger,
                github_run_id=args.github_run_id,
                changed_paths=tuple(paths),
                backend_source=args.backend_source.resolve() if args.backend_source else None,
                impact_map=impact_map,
                frontend_source=args.frontend_source.resolve() if args.frontend_source else None,
                frontend_dist=args.frontend_dist.resolve() if args.frontend_dist else None,
                repository=args.repository.resolve() if args.repository else None,
                backend_env_file=args.backend_env_file,
                python_executable=args.python_executable,
                nginx_source=nginx_source,
                systemd_sources=systemd_sources,
                nginx_target=args.nginx_target,
                nginx_sources=nginx_sources,
                nginx_remove_targets=tuple(item.resolve() for item in args.remove_nginx_target),
                systemd_target_dir=args.systemd_target_dir,
                systemd_remove_units=tuple(args.remove_systemd_unit),
                mediamtx_config_source=args.mediamtx_config_source.resolve() if args.mediamtx_config_source else None,
                health_guard_source=args.health_guard_source.resolve() if args.health_guard_source else None,
                defer_health_guard_restart=args.defer_health_guard_restart,
                backend_service=args.backend_service,
                health_url=args.health_url,
                node_version=args.node_version,
                frontend_package_lock_sha256=args.frontend_package_lock_sha256,
                frontend_api_schema_sha256=args.frontend_api_schema_sha256,
                backend_api_schema_sha256=args.backend_api_schema_sha256,
                compatible_backend_api=args.compatible_backend_api,
                compatible_frontend_api=args.compatible_frontend_api,
                build_budget=budget,
                skip_health=args.skip_health,
            )
        )
        print(json.dumps({"status": transaction["status"], "deployment_id": args.deployment_id}, ensure_ascii=False))
        return 0
    except (ImpactMapError, ProductionDeployError, OSError, ValueError) as exc:
        print(f"production deploy: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
