#!/usr/bin/env python3
"""Verify that a baseline is self-contained and internally consistent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deployment.baseline import BaselineError  # noqa: E402
from deployment.baseline_verification import verify_baseline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--forbidden-reference", action="append", default=[])
    args = parser.parse_args()
    try:
        result = verify_baseline(
            args.baseline,
            additional_forbidden_references=tuple(args.forbidden_reference),
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (BaselineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"verify baseline: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
