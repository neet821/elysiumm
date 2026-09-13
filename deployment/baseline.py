"""Build and verify a self-contained runtime/database baseline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import sqlite3
from typing import Iterable, Mapping


class BaselineError(RuntimeError):
    """The baseline cannot be made self-contained or verified."""


REQUIRED_COMPONENTS = frozenset({"backend", "frontend", "mineradio", "articles"})
BACKEND_VENV = Path("backend/.venv")
BASELINE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
BROAD_RESTORE_DIRECTORIES = frozenset(
    {
        Path("/"),
        Path("/etc"),
        Path("/etc/nginx"),
        Path("/etc/nginx/conf.d"),
        Path("/etc/nginx/sites-enabled"),
        Path("/etc/systemd"),
        Path("/etc/systemd/system"),
        Path("/etc/elysium"),
    }
)


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
    source_root = _resolved(root)
    forbidden = tuple(_resolved(path) for path in forbidden_roots)
    for link in _symlinks(root):
        target = _resolved(link)
        # A live checkout may contain internal links (for example a virtualenv
        # lib64 link or node_modules/.bin wrappers).  copytree(...,
        # symlinks=False) dereferences those safely.  Only reject a link that
        # escapes the copied source tree and lands in a forbidden runtime root.
        if any(_is_within(target, forbidden_root) for forbidden_root in forbidden) and not _is_within(
            target, source_root
        ):
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


def _rewrite_runtime_tree(
    root: Path,
    replacements: Mapping[str, str],
) -> None:
    """Rewrite textual runtime references after the source trees are copied.

    A baseline must continue to boot after its source release directories are
    removed.  Runtime trees can contain generated configuration, shell
    wrappers, virtualenv metadata, or built assets with absolute paths, so
    rewriting only systemd commands is insufficient.  Binary files are left
    untouched; the subsequent residual scan still fails closed for readable
    text files.
    """

    if not replacements:
        return
    roots = [root / name for name in sorted(REQUIRED_COMPONENTS)]
    for runtime_root in roots:
        if not runtime_root.is_dir():
            continue
        for path in runtime_root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                original = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rewritten = rewrite_paths(original, replacements, ())
            if rewritten == original:
                continue
            mode = stat.S_IMODE(path.stat().st_mode)
            os.chmod(path, mode | 0o200)
            try:
                path.write_text(rewritten, encoding="utf-8")
            finally:
                os.chmod(path, mode)


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


def assert_read_only(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if stat.S_IMODE(path.stat().st_mode) & 0o222:
            raise BaselineError(f"baseline path is writable: {path}")


def _safe_relative_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or not value:
        raise BaselineError(f"unsafe baseline relative path: {value!r}")
    return candidate


def _config_restore_targets(inputs: "BaselineInputs") -> dict[str, Path]:
    config_names = set(inputs.config_files)
    target_names = set(inputs.config_restore_targets)
    if config_names != target_names:
        missing = sorted(config_names - target_names)
        unexpected = sorted(target_names - config_names)
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        raise BaselineError("config restore targets must match config files: " + " ".join(details))
    targets: dict[str, Path] = {}
    for relative_name, raw_target in inputs.config_restore_targets.items():
        relative_path = _safe_relative_path(relative_name)
        target = Path(raw_target).expanduser()
        if not target.is_absolute():
            raise BaselineError(f"config restore target must be an absolute file path: {raw_target}")
        normalized = Path(os.path.normpath(str(target)))
        if normalized in BROAD_RESTORE_DIRECTORIES or normalized.name in {"", ".", "/"}:
            raise BaselineError(f"config restore target must be an exact file path: {normalized}")
        if target.is_symlink():
            raise BaselineError(f"config restore target must not be a symlink: {target}")
        if target.exists() and not target.is_file():
            raise BaselineError(f"config restore target must be an exact file path: {target}")
        targets[relative_path.as_posix()] = normalized
    return targets


def _validate_complete_backend_venv(root: Path) -> None:
    virtualenv = root / BACKEND_VENV
    required = (virtualenv / "pyvenv.cfg", virtualenv / "bin/python")
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise BaselineError(
            "baseline backend virtualenv is incomplete; missing " + ", ".join(missing)
        )
    python = virtualenv / "bin/python"
    if not (stat.S_IMODE(python.stat().st_mode) & 0o111) or not os.access(python, os.X_OK):
        raise BaselineError("baseline backend virtualenv python is not executable")
    try:
        result = subprocess.run(
            [str(python), "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"],
            cwd=root / "backend",
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BaselineError("baseline backend virtualenv python cannot run") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise BaselineError("baseline backend virtualenv python failed to run" + (f": {detail[:200]}" if detail else ""))


def _safe_database_relative_path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise BaselineError("baseline database backup path is missing")
    path = _safe_relative_path(value)
    if len(path.parts) < 2 or path.parts[0] != "database":
        raise BaselineError("baseline database backup must be stored below database/")
    return path


def _safe_database_backup_record(values: Mapping[str, object]) -> dict[str, object]:
    allowed = {"status", "path", "driver", "database", "size", "sha256", "source", "verified"}
    for key in values:
        if not isinstance(key, str):
            raise BaselineError("baseline database backup metadata contains a non-string key")
        lowered = key.casefold()
        if any(secret in lowered for secret in ("password", "secret", "token", "credential", "database_url")):
            raise BaselineError("baseline database backup metadata must not contain credentials")
    record = {key: value for key, value in values.items() if key in allowed}
    path = _safe_database_relative_path(record.get("path"))
    record["path"] = path.as_posix()
    return record


def _verify_sqlite_backup(path: Path) -> None:
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error as exc:
        raise BaselineError("baseline SQLite database backup cannot be opened") from exc
    if not result or result[0] != "ok":
        raise BaselineError("baseline SQLite database backup failed integrity check")


def assert_no_forbidden_references(root: Path, forbidden_references: Iterable[str]) -> None:
    forbidden = tuple(item for item in forbidden_references if item)
    if not forbidden:
        return
    scan_roots = [root / name for name in sorted(REQUIRED_COMPONENTS)]
    scan_roots.extend((root / "config/restore", root / "restore"))
    for directory in scan_roots:
        if not directory.is_dir():
            if directory in {root / "config/restore", root / "restore"}:
                raise BaselineError(f"baseline restore path is missing: {directory}")
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for forbidden_path in forbidden:
                if forbidden_path in text:
                    raise BaselineError(
                        f"baseline runtime data references forbidden path: {path}: {forbidden_path}"
                    )


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
    config_restore_targets: Mapping[str, Path] = field(default_factory=dict)
    database_backup_path: Path | None = None
    runtime_dependencies: Mapping[str, Path] = field(default_factory=dict)
    path_replacements: Mapping[str, str] = field(default_factory=dict)
    services: tuple[str, ...] = ()
    service_commands: tuple[str, ...] = ()
    restore_order: tuple[str, ...] = (
        "verify",
        "stop_services",
        "configuration",
        "database_if_requested",
        "start_services",
        "health_verification",
    )


def create_baseline(inputs: BaselineInputs) -> Path:
    root = _resolved(inputs.baseline_root)
    root.mkdir(parents=True, exist_ok=True)
    if set(inputs.components) != REQUIRED_COMPONENTS:
        raise BaselineError(
            "baseline components must be exactly " + ", ".join(sorted(REQUIRED_COMPONENTS))
        )
    if set(inputs.production_revisions) != set(inputs.target_heads):
        raise BaselineError(
            "baseline database revision must exactly match the target Alembic heads: "
            f"current={','.join(inputs.production_revisions) or 'none'} "
            f"target={','.join(inputs.target_heads) or 'none'}"
        )
    forbidden_services = [service for service in inputs.services if "flclash" in service.casefold()]
    if forbidden_services:
        raise BaselineError(
            "baseline restore is not allowed to control FlClash services: "
            + ", ".join(forbidden_services)
        )
    forbidden_commands = [command for command in inputs.service_commands if "flclash" in command.casefold()]
    if forbidden_commands:
        raise BaselineError("baseline service commands must not reference FlClash")
    if not BASELINE_ID_RE.fullmatch(inputs.baseline_id):
        raise BaselineError(f"unsafe baseline id: {inputs.baseline_id!r}")
    config_restore_targets = _config_restore_targets(inputs)
    destination = root / inputs.baseline_id
    if destination.exists() or destination.is_symlink():
        raise BaselineError(f"baseline already exists: {destination}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{inputs.baseline_id}.", dir=root))
    try:
        forbidden_roots = [Path(item) for item in inputs.forbidden_references if item.startswith("/")]
        for component, source in inputs.components.items():
            copy_runtime_tree(source, temporary / component, forbidden_roots)
        for relative_name, source in inputs.runtime_dependencies.items():
            relative_path = _safe_relative_path(relative_name)
            if relative_path.parts[0] not in inputs.components:
                raise BaselineError(
                    f"runtime dependency must live below a copied component: {relative_name}"
                )
            destination_dependency = temporary / relative_path
            resolved_source = _resolved(source)
            if resolved_source.is_dir():
                copy_runtime_tree(resolved_source, destination_dependency, forbidden_roots)
            elif resolved_source.is_file():
                if destination_dependency.exists() or destination_dependency.is_symlink():
                    raise BaselineError(
                        f"baseline dependency destination already exists: {destination_dependency}"
                    )
                destination_dependency.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(resolved_source, destination_dependency)
            else:
                raise BaselineError(f"runtime dependency source does not exist: {resolved_source}")
        _rewrite_runtime_tree(temporary, inputs.path_replacements)
        _validate_complete_backend_venv(temporary)
        baseline_service_commands = tuple(
            rewrite_paths(command, inputs.path_replacements, inputs.forbidden_references)
            for command in inputs.service_commands
        )
        backend_commands = [command for command in baseline_service_commands if "uvicorn" in command]
        if not backend_commands:
            raise BaselineError("baseline service commands must include the backend uvicorn command")
        for command in backend_commands:
            baseline_python = str(destination / BACKEND_VENV / "bin/python")
            if not (
                command.startswith("backend/.venv/bin/python")
                or baseline_python in command
            ) or "-m uvicorn" not in command:
                raise BaselineError(
                    "backend must start through baseline backend/.venv/bin/python -m uvicorn"
                )
        original_dir = temporary / "config/original"
        restore_dir = temporary / "config/restore"
        for relative_name, source in inputs.config_files.items():
            relative_path = _safe_relative_path(relative_name)
            source = source.expanduser()
            if source.is_symlink():
                raise BaselineError(f"config source must not be a symlink: {source}")
            source = _resolved(source)
            if not source.is_file():
                raise BaselineError(f"config source is not a file: {source}")
            original_path = original_dir / relative_path
            restore_path = restore_dir / relative_path
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
            os.chmod(original_path, 0o400)
            os.chmod(restore_path, 0o400 if "env" in relative_path.parts else 0o444)
        (temporary / "database").mkdir(parents=True, exist_ok=True)
        database_backup_path = inputs.database_backup_path
        database_backup_record = _safe_database_backup_record(inputs.database_backup)
        database_backup_relative = database_backup_record["path"]
        if database_backup_path is not None:
            if not database_backup_path.is_file():
                raise BaselineError(f"database backup is not a file: {database_backup_path}")
            destination_backup = temporary / _safe_database_relative_path(database_backup_relative)
            destination_backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(database_backup_path, destination_backup)
            os.chmod(destination_backup, 0o400)
            checksum = _sha256(destination_backup)
            expected_checksum = database_backup_record.get("sha256")
            if expected_checksum is not None and expected_checksum != checksum:
                raise BaselineError("baseline database backup checksum does not match metadata")
            database_backup_record["sha256"] = checksum
            database_backup_record["size"] = destination_backup.stat().st_size
            if str(database_backup_record.get("driver", "")).casefold() == "sqlite":
                _verify_sqlite_backup(destination_backup)
        backup_path = temporary / _safe_database_relative_path(database_backup_record["path"])
        if not backup_path.is_file():
            raise BaselineError("baseline database backup was not copied into the baseline")
        backend_env_relative = next(
            (name for name in inputs.config_files if Path(name).as_posix() == "env/backend.env"),
            None,
        )
        if backend_env_relative is None:
            raise BaselineError("baseline config must include env/backend.env for database restore")
        manifest = {
            "schema_version": 1,
            "baseline_id": inputs.baseline_id,
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "components": {
                name: {
                    "source_path": str(_resolved(source)),
                    "baseline_path": name,
                }
                for name, source in sorted(inputs.components.items())
            },
            "source_origins": {
                **{name: str(_resolved(source)) for name, source in sorted(inputs.components.items())},
                **{
                    relative_name: str(_resolved(source))
                    for relative_name, source in sorted(inputs.runtime_dependencies.items())
                },
            },
            "runtime_dependencies": {
                relative_name: {
                    "source_path": str(_resolved(source)),
                    "baseline_path": relative_name,
                }
                for relative_name, source in sorted(inputs.runtime_dependencies.items())
            },
            "config_files": {
                relative_name: {
                    "source_path": str(_resolved(source)),
                    "restore_target": str(config_restore_targets[relative_name]),
                }
                for relative_name, source in sorted(inputs.config_files.items())
            },
            "service_commands": list(baseline_service_commands),
            "restore_order": list(inputs.restore_order),
            "production_current_revisions": list(inputs.production_revisions),
            "target_alembic_heads": list(inputs.target_heads),
            "database_type": database_backup_record.get("driver", "unknown"),
            "database_backup": database_backup_record,
            "external_shared_dependencies": list(inputs.external_shared_paths),
            "external_shared_paths": list(inputs.external_shared_paths),
            "forbidden_runtime_references": list(inputs.forbidden_references),
            "runtime_paths": {
                "backend_python": "backend/.venv/bin/python",
                "components": sorted(inputs.components),
                "dependencies": sorted(inputs.runtime_dependencies),
            },
            "database_environment": str(backend_env_relative),
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
from urllib.parse import quote, unquote, urlsplit


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
    if not url:
        required = ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME")
        missing = [key for key in required if not values.get(key)]
        if missing:
            raise SystemExit("DATABASE_URL or complete DB_* settings are required")
        url = "mysql+pymysql://{user}:{password}@{host}:{port}/{database}".format(
            user=quote(values["DB_USER"], safe=""),
            password=quote(values["DB_PASSWORD"], safe=""),
            host=values["DB_HOST"],
            port=values["DB_PORT"],
            database=quote(values["DB_NAME"], safe=""),
        )
    parsed = urlsplit(url)
    driver = parsed.scheme.split("+", 1)[0].lower()
    backup = Path(args.backup)
    if driver == "sqlite":
        if parsed.netloc:
            raise SystemExit("SQLite database URL must not contain a host")
        raw_path = unquote(parsed.path)
        target = Path(raw_path.lstrip("/")) if not raw_path.startswith("//") else Path("/" + raw_path.lstrip("/"))
        target = target.resolve()
        if not target.name:
            raise SystemExit("database URL has no SQLite file path")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
        with sqlite3.connect(target) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise SystemExit("restored SQLite database failed integrity check")
        return
    if driver not in {"mysql", "mariadb"}:
        raise SystemExit("unsupported database driver in baseline environment")
    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise SystemExit("database URL has no database name")
    command = [
        "mysql", "--host", parsed.hostname or "127.0.0.1",
        "--port", str(parsed.port or 3306), "--user", unquote(parsed.username or ""), database,
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
        service_stop_commands = "\n".join(
            f"systemctl stop {shlex.quote(service)}" for service in reversed(inputs.services)
        ) or ":"
        service_start_commands = "\n".join(
            f"systemctl start {shlex.quote(service)}" for service in inputs.services
        ) or ":"
        restore_config_commands = []
        for relative_name, target in sorted(config_restore_targets.items()):
            relative_path = _safe_relative_path(relative_name)
            source = f'"$BASELINE_DIR/config/restore/{relative_path.as_posix()}"'
            target_text = shlex.quote(str(target))
            parent_text = shlex.quote(str(target.parent))
            mode = "0600" if "env" in relative_path.parts else "0644"
            restore_config_commands.extend(
                (
                    f"if [[ -L {target_text} ]]; then echo 'refusing symlink restore target' >&2; exit 1; fi",
                    f"ensure_restore_parent {parent_text}",
                    f"install -m {mode} {source} {target_text}",
                )
            )
        (restore / "restore.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nBASELINE_DIR=$(cd \"$(dirname \"${BASH_SOURCE[0]}\")/..\" && pwd)\nensure_restore_parent() {\n  local parent=$1 probe=$1\n  while [[ \"$probe\" != / ]]; do\n    if [[ -L \"$probe\" ]]; then echo \"refusing symlink restore parent: $probe\" >&2; exit 1; fi\n    probe=$(dirname \"$probe\")\n  done\n  install -d -m 0755 \"$parent\"\n}\nif [[ \"$(id -u)\" -ne 0 ]]; then echo 'baseline restore requires root' >&2; exit 1; fi\n\"$BASELINE_DIR/restore/verify.sh\"\nrestore_database=false\nif [[ \"${1:-}\" == '--restore-database' ]]; then restore_database=true; elif [[ -n \"${1:-}\" ]]; then echo \"unknown option: $1\" >&2; exit 2; fi\n# Stop application services before changing their configuration or database.\nPLACEHOLDER_STOP_SERVICES\nif [[ \"$restore_database\" == true ]]; then\n  \"$BASELINE_DIR/backend/.venv/bin/python\" \"$BASELINE_DIR/restore/restore_database.py\" --env-file \"$BASELINE_DIR/config/restore/PLACEHOLDER_BACKEND_ENV\" --backup \"$BASELINE_DIR/$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[\"database_backup\"][\"path\"])' \"$BASELINE_DIR/BASELINE.json\")\"\nfi\nPLACEHOLDER_RESTORE_CONFIGS\nnginx -t\nsystemctl daemon-reload\nPLACEHOLDER_START_SERVICES\nsystemctl reload nginx\nprintf '%s\\n' \"baseline restored from $BASELINE_DIR\"\n",
            encoding="utf-8",
        )
        restore_script = restore / "restore.sh"
        restore_script.write_text(
            restore_script.read_text(encoding="utf-8").replace(
                "PLACEHOLDER_STOP_SERVICES", service_stop_commands
            ).replace("PLACEHOLDER_START_SERVICES", service_start_commands).replace(
                "PLACEHOLDER_BACKEND_ENV", str(backend_env_relative)
            ).replace(
                "PLACEHOLDER_RESTORE_CONFIGS", "\n".join(restore_config_commands)
            ).replace(
                "$(python3 -c",
                '$(\"$BASELINE_DIR/backend/.venv/bin/python\" -c',
            ),
            encoding="utf-8",
        )
        os.chmod(restore / "restore.sh", 0o500)
        (restore / "rollback.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nBASELINE_DIR=$(cd \"$(dirname \"${BASH_SOURCE[0]}\")/..\" && pwd)\nexec \"$BASELINE_DIR/restore/restore.sh\" \"$@\"\n",
            encoding="utf-8",
        )
        os.chmod(restore / "rollback.sh", 0o500)
        checksums = tree_checksums(temporary)
        (temporary / "SHA256SUMS").write_text(
            "".join(f"{digest}  {relative}\n" for relative, digest in sorted(checksums.items())),
            encoding="utf-8",
        )
        assert_no_symlinks(temporary)
        assert_no_forbidden_references(temporary, inputs.forbidden_references)
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
