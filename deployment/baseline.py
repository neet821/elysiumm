"""Build and verify a self-contained runtime/database baseline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import shlex
import shutil
import stat
import tempfile
from typing import Iterable, Mapping


class BaselineError(RuntimeError):
    """The baseline cannot be made self-contained or verified."""


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _symlinks(root: Path) -> Iterable[Path]:
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in (*dirnames, *filenames):
            candidate = directory_path / name
            if candidate.is_symlink():
                yield candidate


def assert_no_forbidden_symlinks(root: Path, forbidden_roots: Iterable[Path]) -> None:
    forbidden = tuple(_resolved(path) for path in forbidden_roots)
    for link in _symlinks(root):
        target = _resolved(link)
        if any(_is_within(target, root) for root in forbidden):
            raise BaselineError(f"baseline source contains a forbidden external symlink: {link} -> {target}")


def copy_runtime_tree(source: Path, destination: Path, forbidden_roots: Iterable[Path] = ()) -> None:
    source = _resolved(source)
    if not source.is_dir():
        raise BaselineError(f"runtime source is not a directory: {source}")
    if destination.exists() or destination.is_symlink():
        raise BaselineError(f"baseline destination already exists: {destination}")
    assert_no_forbidden_symlinks(source, forbidden_roots)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Dereference source links so copied releases do not retain current/release links.
    shutil.copytree(source, destination, symlinks=False)
    assert_no_forbidden_symlinks(destination, forbidden_roots)


def rewrite_paths(text: str, replacements: Mapping[str, str], forbidden_references: Iterable[str]) -> str:
    result = text
    for source, target in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        result = result.replace(source, target)
    leftovers = [item for item in forbidden_references if item and item in result]
    if leftovers:
        raise BaselineError("baseline config still references original paths: " + ", ".join(leftovers))
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_checksums(root: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.name != "SHA256SUMS" and path.is_file() and not path.is_symlink():
            checksums[path.relative_to(root).as_posix()] = _sha256(path)
    return checksums


def verify_checksums(root: Path, checksums: Mapping[str, str]) -> None:
    actual = tree_checksums(root)
    expected = dict(checksums)
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(key for key in set(actual) & set(expected) if actual[key] != expected[key])
        details = []
        if missing:
            details.append("missing=" + ",".join(missing[:5]))
        if extra:
            details.append("extra=" + ",".join(extra[:5]))
        if changed:
            details.append("changed=" + ",".join(changed[:5]))
        raise BaselineError("baseline checksum mismatch: " + " ".join(details))


def assert_no_symlinks(root: Path) -> None:
    link = next(iter(_symlinks(root)), None)
    if link is not None:
        raise BaselineError(f"baseline must be self-contained and contain no symlinks: {link}")


def _safe_relative_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or not value:
        raise BaselineError(f"unsafe baseline relative path: {value!r}")
    return candidate


@dataclass(frozen=True)
class BaselineInputs:
    baseline_root: Path
    baseline_id: str
    components: Mapping[str, Path]
    config_files: Mapping[str, Path]
    forbidden_references: tuple[str, ...]
    external_shared_paths: tuple[str, ...]
    production_revisions: tuple[str, ...]
    target_heads: tuple[str, ...]
    database_backup: Mapping[str, object]
    database_backup_path: Path | None = None
    path_replacements: Mapping[str, str] = field(default_factory=dict)
    services: tuple[str, ...] = ()


def create_baseline(inputs: BaselineInputs) -> Path:
    root = _resolved(inputs.baseline_root)
    root.mkdir(parents=True, exist_ok=True)
    if not inputs.baseline_id or "/" in inputs.baseline_id or ".." in inputs.baseline_id:
        raise BaselineError(f"unsafe baseline id: {inputs.baseline_id!r}")
    destination = root / inputs.baseline_id
    if destination.exists() or destination.is_symlink():
        raise BaselineError(f"baseline already exists: {destination}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{inputs.baseline_id}.", dir=root))
    try:
        forbidden_roots = [Path(item) for item in inputs.forbidden_references if item.startswith("/")]
        for component, source in inputs.components.items():
            copy_runtime_tree(source, temporary / component, forbidden_roots)
        original_dir = temporary / "config/original"
        restore_dir = temporary / "config/restore"
        for relative_name, source in inputs.config_files.items():
            source = _resolved(source)
            if not source.is_file():
                raise BaselineError(f"config source is not a file: {source}")
            original_path = original_dir / relative_name
            restore_path = restore_dir / relative_name
            original_path.parent.mkdir(parents=True, exist_ok=True)
            restore_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, original_path, follow_symlinks=False)
            try:
                text = source.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                shutil.copy2(source, restore_path, follow_symlinks=False)
            else:
                rewritten = rewrite_paths(text, inputs.path_replacements, inputs.forbidden_references)
                restore_path.write_text(rewritten, encoding="utf-8")
            os.chmod(original_path, 0o600 if "env" in relative_name else 0o644)
            os.chmod(restore_path, 0o600 if "env" in relative_name else 0o644)
        (temporary / "database").mkdir(parents=True, exist_ok=True)
        database_backup_path = inputs.database_backup_path
        database_backup_relative = inputs.database_backup.get("path")
        if database_backup_path is not None:
            if not database_backup_path.is_file():
                raise BaselineError(f"database backup is not a file: {database_backup_path}")
            if not isinstance(database_backup_relative, str) or not database_backup_relative:
                database_backup_relative = f"database/{database_backup_path.name}"
            destination_backup = temporary / _safe_relative_path(database_backup_relative)
            destination_backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(database_backup_path, destination_backup)
            os.chmod(destination_backup, 0o400)
            database_backup_record = dict(inputs.database_backup)
            database_backup_record["path"] = str(Path(database_backup_relative).as_posix())
        else:
            database_backup_record = dict(inputs.database_backup)
        manifest = {
            "schema_version": 1,
            "baseline_id": inputs.baseline_id,
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "components": sorted(inputs.components),
            "production_current_revisions": list(inputs.production_revisions),
            "target_alembic_heads": list(inputs.target_heads),
            "database_backup": database_backup_record,
            "external_shared_paths": list(inputs.external_shared_paths),
            "self_contained": {
                "runtime": True,
                "database": True,
                "shared_uploads_and_articles": False,
            },
        }
        (temporary / "BASELINE.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        restore = temporary / "restore"
        restore.mkdir(parents=True, exist_ok=True)
        restore_database = restore / "restore_database.py"
        restore_database.write_text(
            '''#!/usr/bin/env python3
"""Restore a baseline database using only standard-library functionality."""
import argparse
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from urllib.parse import unquote, urlsplit


def load_env(path):
    values = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\\\"'")
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--backup", required=True)
    args = parser.parse_args()
    values = load_env(args.env_file)
    url = values.get("DATABASE_URL", "")
    parsed = urlsplit(url)
    driver = parsed.scheme.split("+", 1)[0].lower()
    backup = Path(args.backup)
    if driver == "sqlite":
        target = Path(unquote(parsed.path))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
        with sqlite3.connect(target) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise SystemExit("restored SQLite database failed integrity check")
        return
    if driver not in {"mysql", "mariadb"}:
        raise SystemExit("unsupported database driver in baseline environment")
    command = [
        "mysql", "--host", parsed.hostname or "127.0.0.1",
        "--port", str(parsed.port or 3306), "--user", unquote(parsed.username or ""),
    ]
    environment = os.environ.copy()
    if parsed.password:
        environment["MYSQL_PWD"] = unquote(parsed.password)
    with backup.open("rb") as source:
        result = subprocess.run(command, stdin=source, stderr=subprocess.PIPE, env=environment, check=False)
    if result.returncode:
        raise SystemExit(result.stderr.decode("utf-8", errors="replace") or "mysql restore failed")


if __name__ == "__main__":
    main()
''',
            encoding="utf-8",
        )
        os.chmod(restore_database, 0o500)
        (restore / "verify.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nBASELINE_DIR=$(cd \"$(dirname \"${BASH_SOURCE[0]}\")/..\" && pwd)\ncd \"$BASELINE_DIR\"\nif find -L \"$BASELINE_DIR\" -type l -print -quit | grep -q .; then echo 'baseline contains a symlink' >&2; exit 1; fi\nsha256sum -c SHA256SUMS\nprintf '%s\\n' 'baseline checksum verification passed'\n",
            encoding="utf-8",
        )
        os.chmod(restore / "verify.sh", 0o500)
        service_commands = "\n".join(
            f"systemctl restart {shlex.quote(service)}" for service in inputs.services
        ) or ":"
        (restore / "rollback.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nBASELINE_DIR=$(cd \"$(dirname \"${BASH_SOURCE[0]}\")/..\" && pwd)\nif [[ \"$(id -u)\" -ne 0 ]]; then echo 'baseline rollback requires root' >&2; exit 1; fi\n\"$BASELINE_DIR/restore/verify.sh\"\nfor file in \"$BASELINE_DIR/config/restore/systemd\"/*; do [[ -f \"$file\" ]] || continue; install -m 0644 \"$file\" \"/etc/systemd/system/$(basename \"$file\")\"; done\nfor file in \"$BASELINE_DIR/config/restore/nginx\"/*; do [[ -f \"$file\" ]] || continue; install -m 0644 \"$file\" \"/etc/nginx/sites-enabled/$(basename \"$file\")\"; done\nif [[ \"${1:-}\" == '--restore-database' ]]; then\n  \"$BASELINE_DIR/restore/restore_database.py\" --env-file \"$BASELINE_DIR/config/restore/env/backend.env\" --backup \"$BASELINE_DIR/$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[\"database_backup\"][\"path\"])' \"$BASELINE_DIR/BASELINE.json\")\"\nfi\nsystemctl daemon-reload\nfor service in PLACEHOLDER_SERVICES; do systemctl restart \"$service\"; done\nsystemctl reload nginx\nprintf '%s\\n' \"baseline restored from $BASELINE_DIR\"\n",
            encoding="utf-8",
        )
        restore_script = restore / "rollback.sh"
        restore_script.write_text(
            restore_script.read_text(encoding="utf-8").replace(
                "for service in PLACEHOLDER_SERVICES; do systemctl restart \"$service\"; done",
                service_commands,
            ),
            encoding="utf-8",
        )
        os.chmod(restore / "rollback.sh", 0o500)
        checksums = tree_checksums(temporary)
        (temporary / "SHA256SUMS").write_text(
            "".join(f"{digest}  {relative}\n" for relative, digest in sorted(checksums.items())),
            encoding="utf-8",
        )
        for path in sorted(temporary.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_dir() and not path.is_symlink():
                os.chmod(path, 0o555)
            elif path.is_file() and not path.is_symlink():
                current_mode = stat.S_IMODE(path.stat().st_mode)
                relative = path.relative_to(temporary).as_posix()
                if relative.startswith("config/original/") or relative.startswith("config/restore/env/") or relative.startswith("database/"):
                    os.chmod(path, 0o400)
                else:
                    os.chmod(path, 0o555 if current_mode & 0o111 else 0o444)
        os.chmod(temporary, 0o555)
        os.replace(temporary, destination)
        return destination
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
