#!/usr/bin/env python3
"""Notify the local backend after MediaMTX closes a recording segment."""

import json
import os
import sys
from urllib import error, request


ENDPOINT = "http://127.0.0.1:8000/api/internal/live/recording-complete"


def main() -> int:
    # MediaMTX supplies `%path %segment_path` as command arguments in the
    # production templates.  Keep the environment form for older/manual
    # invocations, but prefer the concrete segment path when it is provided.
    path = os.getenv("MTX_SEGMENT_PATH", "")
    if len(sys.argv) > 2 and sys.argv[2].strip():
        path = sys.argv[2].strip()
    duration = os.getenv("MTX_SEGMENT_DURATION", "0")
    if not path:
        print("MTX_SEGMENT_PATH is missing", file=sys.stderr)
        return 2
    try:
        duration_seconds = float(duration.rstrip("s"))
    except ValueError:
        duration_seconds = 0
    payload = json.dumps(
        {
            "absolute_path": path,
            "duration_seconds": duration_seconds,
        }
    ).encode("utf-8")
    outgoing = request.Request(
        ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(outgoing, timeout=10) as response:
            return 0 if 200 <= response.status < 300 else 1
    except (error.URLError, TimeoutError) as exc:
        print(f"recording callback failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
