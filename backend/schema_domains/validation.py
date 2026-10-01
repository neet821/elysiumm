from __future__ import annotations


from schema_domains._base import List, Optional, ip_address, urlparse

BOOK_READING_STATUSES = {"unread", "reading", "paused", "completed"}


def _clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _validate_book_cover(value: Optional[str]) -> Optional[str]:
    normalized = _clean_optional_text(value)
    if normalized is None:
        return None
    if normalized.startswith("/") and not normalized.startswith("//"):
        if (
            ".." not in normalized.split("/")
            and "\\" not in normalized
            and "?" not in normalized
            and "#" not in normalized
            and not any(ord(character) < 32 for character in normalized)
        ):
            return normalized
        raise ValueError("封面路径必须位于应用内部")
    parsed = urlparse(normalized)
    if (
        parsed.scheme == "https"
        and parsed.netloc
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    ):
        return normalized
    raise ValueError("封面网址必须使用 HTTPS 或应用内相对路径")


def _validate_book_tags(value: List[str]) -> List[str]:
    if len(value) > 12:
        raise ValueError("最多允许 12 个标签")
    normalized: List[str] = []
    seen = set()
    for tag in value:
        clean = tag.strip()
        if not clean or len(clean) > 40:
            raise ValueError("每个标签必须包含 1 到 40 个字符")
        key = clean.casefold()
        if key in seen:
            raise ValueError("标签不能重复")
        seen.add(key)
        normalized.append(clean)
    return normalized


def _validate_public_https_url(value: Optional[str]) -> Optional[str]:
    normalized = _clean_optional_text(value)
    if normalized is None:
        return None
    parsed = urlparse(normalized)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("外链必须是无凭据的 HTTPS 网址")
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ValueError("外链不能指向本机或内网")
    try:
        address = ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("外链不能指向本机或内网")
    return normalized


MEDIA_STATUSES = {
    "planned",
    "in_progress",
    "paused",
    "completed",
    "dropped",
    "wishlist",
}


MEDIA_METADATA_FIELDS = {
    "title",
    "creator",
    "cover_url",
    "year",
    "summary",
    "tags",
    "source",
    "source_id",
    "external_url",
    "metadata",
}
