#!/usr/bin/env python3
"""CLI for the repository's versioned release impact map."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deployment.release_impact import (  # noqa: E402
    ImpactMapError,
    changed_paths_from_git,
    resolve_impact,
    resolve_impact_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--impact-map", type=Path, default=None)
    parser.add_argument("--path", dest="paths", action="append", default=[])
    parser.add_argument("--base")
    parser.add_argument("--head")
    args = parser.parse_args()
    root = args.root.resolve()
    impact_map = (args.impact_map or root / "release-impact.yml").resolve()
    try:
        paths = list(args.paths)
        if args.base or args.head:
            if not args.base or not args.head:
                parser.error("--base and --head must be supplied together")
            paths.extend(changed_paths_from_git(root, args.base, args.head))
        print(resolve_impact_json(resolve_impact(paths, impact_map=impact_map, root=root)), end="")
    except (ImpactMapError, OSError) as exc:
        print(f"release impact: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
