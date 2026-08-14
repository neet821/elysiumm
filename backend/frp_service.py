import os
import re
import shutil
import subprocess
import tomllib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
import base64


@dataclass(frozen=True)
class FrpPaths:
    root: Path
    binary: Path
    config: Path
    log: Path
    backup_dir: Path
    service_name: str
    dry_run: bool


def get_frp_paths() -> FrpPaths:
    root = Path(os.getenv("FRP_ROOT", "/home/frp"))
    config = Path(os.getenv("FRP_CONFIG", str(root / "frps.toml")))
    log = Path(os.getenv("FRP_LOG", str(root / "frps.log")))
    backup_dir = Path(os.getenv("FRP_BACKUP_DIR", str(root / "backups")))
    binary = Path(os.getenv("FRP_BINARY", str(root / "frps")))
    return FrpPaths(
        root=root,
        binary=binary,
        config=config,
        log=log,
        backup_dir=backup_dir,
        service_name=os.getenv("FRP_SERVICE_NAME", "frps.service"),
        dry_run=os.getenv("FRP_DRY_RUN", "").lower() in {"1", "true", "yes"},
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def validate_config(content: str) -> dict[str, Any]:
    try:
        parsed = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"TOML 格式错误: {exc}") from exc

    bind_port = parsed.get("bindPort")
    if not isinstance(bind_port, int):
        raise ValueError("配置必须包含整数 bindPort")
    return parsed


def config_summary(content: str) -> dict[str, Any]:
    parsed = validate_config(content)
    web_server = parsed.get("webServer", {})
    auth = parsed.get("auth", {})
    return {
        "bind_port": parsed.get("bindPort"),
        "vhost_http_port": parsed.get("vhostHTTPPort"),
        "dashboard_addr": web_server.get("addr"),
        "dashboard_port": web_server.get("port"),
        "dashboard_user": web_server.get("user"),
        "has_token": bool(auth.get("token")),
        "log_file": parsed.get("log", {}).get("to"),
    }


def dashboard_settings(content: str) -> dict[str, Any]:
    parsed = validate_config(content)
    web_server = parsed.get("webServer", {})
    return {
        "addr": web_server.get("addr") or "127.0.0.1",
        "port": web_server.get("port"),
        "user": web_server.get("user"),
        "password": web_server.get("password"),
    }


def backup_config(paths: FrpPaths | None = None) -> Path:
    paths = paths or get_frp_paths()
    if not paths.config.exists():
        raise FileNotFoundError(f"frp 配置不存在: {paths.config}")
    paths.backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup_path = paths.backup_dir / f"{paths.config.name}.{timestamp}.bak"
    shutil.copy2(paths.config, backup_path)
    return backup_path


def list_config_backups(paths: FrpPaths | None = None) -> list[dict[str, Any]]:
    paths = paths or get_frp_paths()
    if not paths.backup_dir.exists():
        return []
    backups = sorted(paths.backup_dir.glob(f"{paths.config.name}.*.bak"), reverse=True)
    return [
        {
            "name": backup.name,
            "path": str(backup),
            "file_size": backup.stat().st_size,
            "created_at": datetime.fromtimestamp(backup.stat().st_mtime).isoformat(),
        }
        for backup in backups
    ]


def write_config(content: str, paths: FrpPaths | None = None) -> dict[str, Any]:
    paths = paths or get_frp_paths()
    summary = config_summary(content)
    backup_path = backup_config(paths)
    paths.config.write_text(content, encoding="utf-8")
    return {
        "config_path": str(paths.config),
        "backup_path": str(backup_path),
        "summary": summary,
    }


def restore_config_backup(backup_name: str, paths: FrpPaths | None = None) -> dict[str, Any]:
    paths = paths or get_frp_paths()
    if "/" in backup_name or "\\" in backup_name:
        raise ValueError("备份名称无效")
    backup_path = paths.backup_dir / backup_name
    if not backup_path.exists():
        raise FileNotFoundError(f"frp 配置备份不存在: {backup_name}")
    content = read_text(backup_path)
    validate_config(content)
    current_backup = backup_config(paths)
    shutil.copy2(backup_path, paths.config)
    return {
        "config_path": str(paths.config),
        "restored_from": str(backup_path),
        "current_backup": str(current_backup),
    }


def run_systemctl(action: str, paths: FrpPaths | None = None) -> dict[str, Any]:
    paths = paths or get_frp_paths()
    if action not in {"start", "stop", "restart"}:
        raise ValueError("不支持的 frp 操作")
    if paths.dry_run:
        return {
            "action": action,
            "status": "dry_run",
            "stdout": "",
            "stderr": "",
        }

    command = ["systemctl", action, paths.service_name]
    if os.geteuid() != 0:
        command = ["sudo", "-n", *command]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"systemctl {action} 失败")
    return {
        "action": action,
        "status": "completed",
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def service_status(paths: FrpPaths | None = None) -> dict[str, Any]:
    paths = paths or get_frp_paths()
    if paths.dry_run:
        return {
            "active": "dry_run",
            "detail": "FRP_DRY_RUN enabled",
        }

    active = subprocess.run(
        ["systemctl", "is-active", paths.service_name],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    detail = subprocess.run(
        ["systemctl", "status", paths.service_name, "--no-pager", "-l"],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    return {
        "active": active.stdout.strip() or active.stderr.strip() or "unknown",
        "detail": detail.stdout.strip() or detail.stderr.strip(),
    }


def tail_log(lines: int = 200, paths: FrpPaths | None = None) -> str:
    paths = paths or get_frp_paths()
    if not paths.log.exists():
        return ""
    all_lines = paths.log.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(all_lines[-max(1, min(lines, 1000)):])


def recent_proxy_names(log_text: str) -> list[str]:
    names = []
    seen = set()
    for match in re.finditer(r"\[[^\]]+\]\s+\[([A-Za-z0-9_.-]+)\]", log_text):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def dashboard_proxy_list(config_content: str, paths: FrpPaths | None = None) -> dict[str, Any]:
    paths = paths or get_frp_paths()
    if paths.dry_run or not config_content:
        return {"available": False, "proxies": [], "error": None}

    settings = dashboard_settings(config_content)
    port = settings.get("port")
    if not port:
        return {"available": False, "proxies": [], "error": "dashboard port not configured"}

    auth_header = None
    if settings.get("user") and settings.get("password"):
        token = f"{settings['user']}:{settings['password']}".encode("utf-8")
        auth_header = f"Basic {base64.b64encode(token).decode('ascii')}"

    proxies: list[dict[str, Any]] = []
    errors = []
    for proxy_type in ("tcp", "udp", "http", "https"):
        url = f"http://127.0.0.1:{port}/api/proxy/{proxy_type}"
        request = Request(url)
        if auth_header:
            request.add_header("Authorization", auth_header)
        try:
            with urlopen(request, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            for item in payload.get("proxies", []):
                item["type"] = proxy_type
                proxies.append(item)
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(f"{proxy_type}: {exc}")

    return {
        "available": bool(proxies),
        "proxies": proxies,
        "error": "; ".join(errors) if errors and not proxies else None,
    }


def status_snapshot(paths: FrpPaths | None = None) -> dict[str, Any]:
    paths = paths or get_frp_paths()
    config_content = read_text(paths.config) if paths.config.exists() else ""
    summary = config_summary(config_content) if config_content else {}
    log_text = tail_log(200, paths)
    return {
        "root": str(paths.root),
        "service_name": paths.service_name,
        "service": service_status(paths),
        "paths": {
            "binary": str(paths.binary),
            "config": str(paths.config),
            "log": str(paths.log),
            "backup_dir": str(paths.backup_dir),
        },
        "exists": {
            "root": paths.root.exists(),
            "binary": paths.binary.exists(),
            "config": paths.config.exists(),
            "log": paths.log.exists(),
        },
        "config_summary": summary,
        "recent_proxies": recent_proxy_names(log_text),
        "dashboard_proxies": dashboard_proxy_list(config_content, paths),
        "backups": list_config_backups(paths),
    }
