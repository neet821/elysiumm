from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from .markdown_renderer import (
    MARKDOWN as MARKDOWN,
    _HtmlSanitizer as _HtmlSanitizer,
    _sanitize_html as _sanitize_html,
    quote_path as quote_path,
    render_article,
)
from .note_parser import (
    CATEGORY_LABELS as CATEGORY_LABELS,
    COVER_AREA_PATTERN as COVER_AREA_PATTERN,
    EDIT_INFO_CALLOUT_PATTERN as EDIT_INFO_CALLOUT_PATTERN,
    EXCERPT_KEYS as EXCERPT_KEYS,
    FRONTMATTER_KEYS as FRONTMATTER_KEYS,
    IMAGE_WIKILINK_PATTERN as IMAGE_WIKILINK_PATTERN,
    MARKDOWN_IMAGE_PATTERN as MARKDOWN_IMAGE_PATTERN,
    TITLE_FOLLOWED_YAML_PATTERN as TITLE_FOLLOWED_YAML_PATTERN,
    _classify as _classify,
    _clean_text as _clean_text,
    _date_text as _date_text,
    _first_heading as _first_heading,
    _first_image_reference as _first_image_reference,
    _frontmatter_value as _frontmatter_value,
    _has_frontmatter_value as _has_frontmatter_value,
    _is_template_path as _is_template_path,
    _is_yes as _is_yes,
    _media_reference as _media_reference,
    _normalize_task_list as _normalize_task_list,
    _parse_note as _parse_note,
    _strip_obsidian_cover_area as _strip_obsidian_cover_area,
    _strip_obsidian_edit_panel as _strip_obsidian_edit_panel,
    _strip_obsidian_metadata_match_panel as _strip_obsidian_metadata_match_panel,
    _yaml_data as _yaml_data,
)


class ArticleNotFoundError(Exception):
    pass


class ArticleForbiddenError(Exception):
    pass


def _is_inside(root: Path, candidate: Path) -> bool:
    try:
        os.path.commonpath((str(root), str(candidate)))
        return os.path.commonpath((str(root), str(candidate))) == str(root)
    except ValueError:
        return False


class ArticleStore:
    def __init__(self, root_dir: str | Path, media_root: str | Path | None = None, include_root_files: bool = True):
        self.article_root = Path(root_dir).expanduser().resolve()
        self.asset_root = Path(media_root or self.article_root).expanduser().resolve()
        self.include_root_files = include_root_files
        self.cache: dict[str, dict[str, Any]] = {}

    @classmethod
    def from_environment(cls) -> "ArticleStore":
        # Articles are served by FastAPI now.  The default deliberately stays
        # inside the shared root so a release never falls back to a deleted
        # workstation/archive checkout.  Production may still override these
        # roots while the data-to-shared migration is being completed.
        from config import config

        article_root = Path(
            os.getenv("ARTICLE_ROOT", str(config.PUBLIC_SYNC_STORAGE_DIR / "articles"))
        )
        media_root = Path(
            os.getenv("MEDIA_ROOT", str(config.PUBLIC_SYNC_STORAGE_DIR / "media"))
        )
        return cls(article_root, media_root, include_root_files=False)

    def _markdown_files(self) -> list[Path]:
        files: list[Path] = []
        for directory, dirnames, filenames in os.walk(self.article_root):
            dirnames[:] = [name for name in dirnames if not name.startswith(".")]
            for filename in filenames:
                if not filename.startswith(".") and Path(filename).suffix.lower() == ".md":
                    files.append(Path(directory) / filename)
        return files

    def _read_record(self, file: Path) -> dict[str, Any] | None:
        relative_path = file.relative_to(self.article_root).as_posix()
        if not self.include_root_files and "/" not in relative_path:
            return None
        if _is_template_path(relative_path):
            return None
        source = file.read_text(encoding="utf-8")
        data, body, parsed_title, cover, excerpt = _parse_note(source, file.stem)
        classification = _classify(relative_path, data)
        if not classification:
            return None
        content_type, type_name = classification
        raw_type = _clean_text(data.get("type") or data.get("kind") or data.get("content_type")).lower()
        parts = [part.lower() for part in Path(relative_path).parts]
        managed_title = content_type in {"article", "essay", "record"} and (
            raw_type in {"article", "essay", "movie", "album", "book", "game"}
            or any(part in {"文章", "随笔", "记录", "articles", "essays", "records"} for part in parts)
        )
        stat = file.stat()
        sync_keys = ("同步到网站", "sync_to_site", "syncToSite")
        sync_value = _frontmatter_value(data, sync_keys)
        item: dict[str, Any] = {
            "slug": str(Path(relative_path).with_suffix("")).replace(os.sep, "/"),
            "title": file.stem if managed_title else parsed_title,
            "excerpt": excerpt,
            "cover": cover,
            "date": _date_text(data.get("date") or data.get("published") or data.get("created") or data.get("taken_at") or data.get("watched_at") or data.get("listened_at") or data.get("read_at") or data.get("played_at")),
            "tags": [_clean_text(value) for value in data.get("tags", [])] if isinstance(data.get("tags"), list) else [],
            "category": _clean_text(data.get("category") or data.get("type") or data.get("content_type")),
            "type": type_name,
            "contentType": content_type,
            "categoryLabel": CATEGORY_LABELS[content_type],
            "published": content_type not in {"article", "essay"} or not _has_frontmatter_value(data, sync_keys) or _is_yes(sync_value),
            "link": data.get("link") is not False,
            "createdAt": _date_text(data.get("created_at") or data.get("createdAt")),
            "updatedAt": _date_text(data.get("updated_at") or data.get("updatedAt")) or datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            "location": _clean_text(data.get("location") or data.get("地点")),
            "author": _clean_text(data.get("author") or data.get("creator") or data.get("作者") or data.get("director") or data.get("导演")),
            "year": _clean_text(data.get("year") or data.get("年份")),
            "country": _clean_text(data.get("country") or data.get("国家")),
            "language": _clean_text(data.get("language") or data.get("语言")),
            "review": _clean_text(data.get("review") or data.get("个人评论")),
        }
        if not item["cover"] and content_type == "photo":
            image = IMAGE_WIKILINK_PATTERN.search(body)
            if image:
                item["cover"] = image.group(1).strip()
        self.cache[item["slug"]] = {**item, "file": file, "body": body, "directory": file.parent}
        return item

    def list_articles(self) -> list[dict[str, Any]]:
        self.cache.clear()
        items = [item for file in self._markdown_files() if (item := self._read_record(file)) and item["published"]]
        return sorted(items, key=lambda item: item["date"] or item["updatedAt"], reverse=True)

    def get_article(self, slug: str) -> dict[str, Any]:
        self.list_articles()
        record = self.cache.get(slug)
        if not record:
            raise ArticleNotFoundError()
        return render_article(record)

    def _find_by_name(self, name: str) -> Path | None:
        for directory, dirnames, filenames in os.walk(self.article_root):
            dirnames[:] = [item for item in dirnames if not item.startswith(".")]
            if name in filenames:
                return Path(directory) / name
        return None

    def resolve_media(self, slug: str, relative_path: str) -> Path:
        self.list_articles()
        record = self.cache.get(slug)
        if not record:
            raise ArticleNotFoundError()
        decoded = unquote(relative_path)
        for candidate, root in ((Path(record["directory"]) / decoded, Path(record["directory"])), (self.asset_root / decoded, self.asset_root)):
            candidate = candidate.resolve(strict=False)
            root = root.resolve()
            if _is_inside(root, candidate):
                if candidate.is_file():
                    return candidate
                fallback = self._find_by_name(Path(decoded).name)
                if fallback:
                    fallback = fallback.resolve(strict=False)
                    if _is_inside(self.article_root, fallback) or _is_inside(self.asset_root, fallback):
                        return fallback
        raise ArticleForbiddenError()


def media_type_for(path: Path) -> str:
    node_types = {
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".pdf": "application/pdf",
    }
    return node_types.get(path.suffix.lower(), "application/octet-stream")
