"""Read-only legacy ``/data`` access audit for release gates and operations."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import os
from pathlib import Path
import re
import subprocess
from typing import Iterable


@dataclass(frozen=True)
class LegacyFinding:
    source: str
    location: str


def _contains_legacy(value: str, legacy_path: str) -> bool:
    base = legacy_path.rstrip("/")
    if not base:
        return False
    boundary = re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(base)}(?:/|$|[\s'\"=:,;])")
    return boundary.search(value) is not None


def scan_text_paths(paths: Iterable[Path], legacy_path: str) -> list[LegacyFinding]:
    findings: list[LegacyFinding] = []
    for path in paths:
        if not path.is_file() or path.is_symlink():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            if _contains_legacy(line, legacy_path):
                findings.append(LegacyFinding("text", f"{path}:{line_number}"))
    return findings


DEFAULT_EXCLUDED_REPOSITORY_PATHS = frozenset(
    {
        "deployment/legacy_path_scan.py",
        "scripts/check-legacy-paths.py",
        "tests/test_legacy_path_scan.py",
        "docs/migrations/data-to-shared.md",
        "docs/migration/elysiumm-server-layout.md",
        # This guide contains the literal legacy path in migration commands;
        # it is operator documentation, not a runtime consumer.
        "docs/deployment.md",
    }
)


def _candidate_repository_files(root: Path, excluded_paths: Iterable[str] = ()) -> list[Path]:
    result: list[Path] = []
    excluded = {Path(item).as_posix() for item in excluded_paths}
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
            check=True,
            capture_output=True,
            text=True,
        )
        for raw in completed.stdout.splitlines():
            candidate = root / raw
            if (
                candidate.is_file()
                and ".git" not in candidate.parts
                and candidate.relative_to(root).as_posix() not in excluded
            ):
                result.append(candidate)
    except (OSError, subprocess.SubprocessError):
        for directory, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in {".git", ".venv", "node_modules", "__pycache__"}]
            result.extend(
                Path(directory) / name
                for name in filenames
                if (Path(directory) / name).relative_to(root).as_posix() not in excluded
            )
    return result


def scan_processes(proc_root: Path, legacy_path: str) -> list[LegacyFinding]:
    findings: list[LegacyFinding] = []
    if not proc_root.is_dir():
        return findings
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = entry.name
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace")
            cwd = os.readlink(entry / "cwd")
            environment = (entry / "environ").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace")
        except OSError:
            continue
        if _contains_legacy(command, legacy_path):
            findings.append(LegacyFinding("process-command", pid))
        if _contains_legacy(cwd, legacy_path):
            findings.append(LegacyFinding("process-cwd", pid))
        if _contains_legacy(environment, legacy_path):
            findings.append(LegacyFinding("process-environment", pid))
        try:
            for descriptor in (entry / "fd").iterdir():
                try:
                    target = os.readlink(descriptor)
                except OSError:
                    continue
                if _contains_legacy(target, legacy_path):
                    findings.append(LegacyFinding("process-fd", pid))
                    break
        except OSError:
            pass
    return findings


def scan_git_repository(
    repository: Path,
    revision: str,
    legacy_path: str,
    excluded_paths: Iterable[str] = DEFAULT_EXCLUDED_REPOSITORY_PATHS,
) -> list[LegacyFinding]:
    """Scan a commit in a bare or normal repository without making a checkout."""

    repository = repository.expanduser().resolve()
    excluded = {Path(item).as_posix() for item in excluded_paths}
    base = legacy_path.rstrip("/")
    result = subprocess.run(
        [
            "git",
            "--git-dir",
            str(repository),
            "grep",
            "--no-color",
            "-n",
            "-F",
            base,
            revision,
            "--",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "git legacy-path scan failed")
    findings: list[LegacyFinding] = []
    for raw in result.stdout.splitlines():
        parts = raw.split(":", 3)
        if len(parts) != 4:
            continue
        _revision, path, line_number, text = parts
        if path in excluded:
            continue
        if _contains_legacy(text, legacy_path):
            findings.append(LegacyFinding("repository", f"{revision}:{path}:{line_number}"))
    return findings


def scan_legacy_paths(
    *,
    repository_root: Path,
    legacy_path: str = "/data/",
    systemd_root: Path = Path("/etc/systemd/system"),
    nginx_root: Path = Path("/etc/nginx"),
    proc_root: Path | None = Path("/proc"),
    excluded_repository_paths: Iterable[str] = DEFAULT_EXCLUDED_REPOSITORY_PATHS,
    git_repository: Path | None = None,
    git_revision: str | None = None,
) -> dict[str, object]:
    if not legacy_path or not legacy_path.startswith("/"):
        raise ValueError("legacy path must be absolute")
    repository_root = repository_root.expanduser().resolve()
    findings: list[LegacyFinding] = []
    if git_repository is not None and git_revision:
        try:
            findings.extend(
                scan_git_repository(
                    git_repository,
                    git_revision,
                    legacy_path,
                    excluded_paths=excluded_repository_paths,
                )
            )
            text_paths: list[Path] = []
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            findings.append(LegacyFinding("repository-error", str(exc)))
            text_paths = []
    else:
        text_paths = _candidate_repository_files(repository_root, excluded_repository_paths)
    text_paths.extend(path for path in systemd_root.rglob("*") if path.is_file()) if systemd_root.is_dir() else None
    text_paths.extend(path for path in nginx_root.rglob("*") if path.is_file()) if nginx_root.is_dir() else None
    findings.extend(scan_text_paths(text_paths, legacy_path))
    if proc_root is not None:
        findings.extend(scan_processes(proc_root, legacy_path))
    unique = sorted({(item.source, item.location) for item in findings})
    return {
        "legacy_path": legacy_path,
        "clean": not unique,
        "findings": [asdict(LegacyFinding(source, location)) for source, location in unique],
        "scanned": {
            "repository": str(repository_root),
            "systemd": str(systemd_root),
            "nginx": str(nginx_root),
            "processes": str(proc_root) if proc_root is not None else None,
        },
    }


__all__ = [
    "DEFAULT_EXCLUDED_REPOSITORY_PATHS",
    "LegacyFinding",
    "scan_legacy_paths",
    "scan_processes",
    "scan_git_repository",
    "scan_text_paths",
]
