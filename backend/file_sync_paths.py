from urllib.parse import unquote, urlparse


def relative_item_path(href: str, current_path: str, mount_url: str) -> str:
    raw = unquote(href or "").replace("\\", "/").lstrip("/")
    mount = urlparse(mount_url).path.strip("/")
    if mount and (raw == mount or raw.startswith(f"{mount}/")):
        raw = raw[len(mount):].lstrip("/")
    current = current_path.strip("/")
    if current and (raw == current or raw.startswith(f"{current}/")):
        raw = raw[len(current):].lstrip("/")
    is_directory = raw.endswith("/") or href.endswith("/")
    raw = raw.strip("/")
    return f"{raw}/" if raw and is_directory else raw
