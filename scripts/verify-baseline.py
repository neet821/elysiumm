#!/usr/bin/env python3
"""Verify that a baseline is self-contained and internally consistent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deployment.baseline import BaselineError, assert_no_symlinks, verify_checksums  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--forbidden-reference", action="append", default=[])
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    try:
        if not baseline.is_dir():
            raise BaselineError(f"baseline is not a directory: {baseline}")
        manifest = json.loads((baseline / "BASELINE.json").read_text(encoding="utf-8"))
        if manifest.get("self_contained", {}).get("runtime") is not True:
            raise BaselineError("baseline manifest does not declare self-contained runtime")
        if manifest.get("self_contained", {}).get("database") is not True:
            raise BaselineError("baseline manifest does not declare self-contained database")
        checksums: dict[str, str] = {}
        for raw in (baseline / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            if raw.strip():
                digest, relative = raw.split("  ", 1)
                checksums[relative] = digest
        verify_checksums(baseline, checksums)
        assert_no_symlinks(baseline)
        for path in (baseline / "config/restore").rglob("*"):
            if path.is_file():
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                for forbidden in args.forbidden_reference:
                    if forbidden and forbidden in text:
                        raise BaselineError(f"restore config references original path: {path}: {forbidden}")
        print(json.dumps({"baseline": str(baseline), "verified": True}, ensure_ascii=False, sort_keys=True))
        return 0
    except (BaselineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"verify baseline: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
