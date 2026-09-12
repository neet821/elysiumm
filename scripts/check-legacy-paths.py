#!/usr/bin/env python3
"""Audit repository/configuration/processes for legacy /data access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deployment.legacy_path_scan import (  # noqa: E402
    DEFAULT_EXCLUDED_REPOSITORY_PATHS,
    scan_legacy_paths,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--legacy-path", default="/srv/services/elysium/" + "data/")
    parser.add_argument("--systemd-root", type=Path, default=Path("/etc/systemd/system"))
    parser.add_argument("--nginx-root", type=Path, default=Path("/etc/nginx"))
    parser.add_argument("--proc-root", type=Path, default=Path("/proc"))
    parser.add_argument("--git-dir", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--no-processes", action="store_true")
    args = parser.parse_args()
    result = scan_legacy_paths(
        repository_root=args.root,
        legacy_path=args.legacy_path,
        systemd_root=args.systemd_root,
        nginx_root=args.nginx_root,
        proc_root=None if args.no_processes else args.proc_root,
        excluded_repository_paths=(*DEFAULT_EXCLUDED_REPOSITORY_PATHS, *args.exclude),
        git_repository=args.git_dir,
        git_revision=args.revision,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
