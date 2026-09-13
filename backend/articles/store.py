from __future__ import annotations

import html
import os
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import yaml
from markdown_it import MarkdownIt


CATEGORY_LABELS = {"article": "文章", "essay": "随笔", "photo": "照片", "record": "记录"}
FRONTMATTER_KEYS = ("cover", "image", "thumbnail")
EXCERPT_KEYS = ("description", "excerpt", "summary", "preview")
COVER_AREA_PATTERN = re.compile(r"<!--\s*elysium-cover:start\s*-->[\s\S]*?<!--\s*elysium-cover:end\s*-->", re.I)
EDIT_INFO_CALLOUT_PATTERN = re.compile(r"^\s*>\s*\[!info\]-\s*编辑信息\s*\n(?:(?:^\s*>.*(?:\n|$))|^\s*\n)*", re.I | re.M)
IMAGE_WIKILINK_PATTERN = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
TITLE_FOLLOWED_YAML_PATTERN = re.compile(
    r"^\s*#\s+(.+?)\s*\n+\s*\n((?:[A-Za-z_][\w-]*\s*:\s*.*\n?)+)\s*\n", re.M
)
MARKDOWN = MarkdownIt("commonmark", {"html": True}).enable("table")


class ArticleNotFoundError(Exception):
    pass


class ArticleForbiddenError(Exception):
    pass


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value).strip()


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _clean_text(value)


def _normalize_task_list(source: str) -> str:
    return re.sub(r"^(\s*)\[([ xX])\]\s+", r"\1- [\2] ", source, flags=re.M)


def _strip_obsidian_edit_panel(source: str) -> str:
    source = re.sub(
        r"<!--\s*elysium-edit-panel:start\s*-->[\s\S]*?<!--\s*elysium-edit-panel:end\s*-->",
        "",
        source,
        flags=re.I,
    )
    return EDIT_INFO_CALLOUT_PATTERN.sub("", source)


def _media_reference(value: Any) -> str:
    text = _clean_text(value)
    match = re.fullmatch(r"!??\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text)
    return match.group(1).strip() if match else text


def _first_image_reference(source: str) -> str:
    wikilink = IMAGE_WIKILINK_PATTERN.search(source)
    if wikilink:
        return wikilink.group(1).strip()
    markdown = re.search(r"!\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))", source)
    return ((markdown.group(1) or markdown.group(2)) if markdown else "").strip()


def _strip_obsidian_cover_area(source: str) -> str:
    def replace(area: re.Match[str]) -> str:
        image = _first_image_reference(area.group(0))
        return f"![[{image}]]" if image else ""

    return re.sub(r"^\s*##\s+封面\s*$", "", COVER_AREA_PATTERN.sub(replace, source), flags=re.I | re.M)


def _frontmatter_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    return next((data[key] for key in keys if key in data), None)


def _has_frontmatter_value(data: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(key in data for key in keys)


def _is_yes(value: Any) -> bool:
    return _clean_text(value).lower() in {"是", "yes", "true", "1", "on"}


def _first_heading(source: str) -> str:
    match = re.search(r"^\s*#\s+(.+?)\s*$", source, flags=re.M)
    return match.group(1).strip() if match else ""


def _yaml_data(source: str) -> dict[str, Any]:
    parsed = yaml.safe_load(source)
    return parsed if isinstance(parsed, dict) else {}


def _parse_note(source: str, fallback_title: str) -> tuple[dict[str, Any], str, str, str, str]:
    data: dict[str, Any] = {}
    body = source
    if source.lstrip().startswith("---"):
        match = re.match(r"^\s*---\s*\n([\s\S]*?)\n---\s*(?:\n|$)", source)
        if match:
            data = _yaml_data(match.group(1))
            body = source[match.end() :]
    else:
        match = TITLE_FOLLOWED_YAML_PATTERN.search(source)
        if match:
            data = _yaml_data(match.group(2))
            body = source[: match.start()] + source[match.end() :]
    body = _normalize_task_list(body)
    title = _clean_text(data.get("title")) or _first_heading(source) or fallback_title or "Untitled"
    cover_area = COVER_AREA_PATTERN.search(body)
    cover = _first_image_reference(cover_area.group(0)) if cover_area else ""
    if not cover:
        cover = next((_media_reference(data.get(key)) for key in FRONTMATTER_KEYS if _media_reference(data.get(key))), "")
    excerpt_key = next((key for key in EXCERPT_KEYS if key in data), None)
    if excerpt_key:
        excerpt = _clean_text(data[excerpt_key])
    else:
        excerpt_body = _strip_obsidian_cover_area(_strip_obsidian_edit_panel(body))
        excerpt_body = re.sub(r"^---[\s\S]*?---\s*", "", excerpt_body, flags=re.M)
        excerpt_body = re.sub(r"^\s*#.*$", "", excerpt_body, flags=re.M)
        excerpt_body = re.sub(r"!\[\[.*?\]\]", "", excerpt_body)
        excerpt_body = re.sub(r"[#>*_`\[\]]", "", excerpt_body)
        excerpt = next((part.strip() for part in re.split(r"\n\s*\n", excerpt_body) if part.strip()), "")
    return data, body, title, cover, re.sub(r"\s+", " ", excerpt).strip()[:280]


def _classify(relative_path: str, data: dict[str, Any]) -> tuple[str, str] | None:
    parts = [part.lower() for part in Path(relative_path).parts]
    if _is_template_path(relative_path):
        return None
    raw_type = _clean_text(data.get("type") or data.get("kind") or data.get("content_type")).lower()
    if raw_type in {"movie", "album", "book", "game"}:
        return "record", raw_type
    if raw_type in {"essay", "随笔"}:
        return "essay", "essay"
    if raw_type in {"photo", "image", "picture", "照片"}:
        return "photo", "image" if raw_type == "image" else "photo"
    if raw_type in {"article", "文章"}:
        return "article", "article"
    if any(part in {"照片", "photos", "images"} for part in parts):
        return "photo", "photo"
    if any(part in {"随笔", "essays"} for part in parts):
        return "essay", "essay"
    if any(part in {"文章", "articles"} for part in parts):
        return "article", "article"
    if any(part in {"记录", "records"} for part in parts):
        return "record", "record"
    if len(parts) == 1:
        return "article", raw_type or "article"
    return None


def _is_template_path(relative_path: str) -> bool:
    parts = [part.lower() for part in Path(relative_path).parts]
    return any(part in {"模板", "templates", "template"} for part in parts)


def _is_inside(root: Path, candidate: Path) -> bool:
    try:
        os.path.commonpath((str(root), str(candidate)))
        return os.path.commonpath((str(root), str(candidate))) == str(root)
    except ValueError:
        return False


class _HtmlSanitizer(HTMLParser):
    allowed_tags = {
        "a", "abbr", "acronym", "address", "article", "aside", "b", "blockquote", "br", "caption", "code", "col", "colgroup",
        "dd", "del", "div", "dl", "dt", "em", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
        "header", "hr", "i", "img", "ins", "kbd", "li", "main", "ol", "p", "pre", "q", "s", "samp", "section", "small",
        "span", "strike", "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul", "var",
    }
    void_tags = {"br", "col", "hr", "img"}
    drop_content_tags = {"embed", "iframe", "object", "script", "style"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.drop_depth = 0

    @staticmethod
    def _safe_url(value: str, *, image: bool = False) -> bool:
        normalized = value.strip().lower()
        if not normalized or normalized.startswith(("#", "/", "./", "../")):
            return True
        match = re.match(r"^([a-z][a-z0-9+.-]*):", normalized)
        if not match:
            return True
        allowed = {"http", "https", "ftp", "mailto", "tel"}
        return match.group(1) in (allowed | ({"data"} if image else set()))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.drop_content_tags:
            self.drop_depth += 1
            return
        if self.drop_depth or tag not in self.allowed_tags:
            return
        allowed_attrs = {"a": {"href", "name", "target", "rel"}, "img": {"src", "alt", "title"}, "code": {"class"}}
        rendered = []
        for name, value in attrs:
            name = name.lower()
            if name not in allowed_attrs.get(tag, set()) or value is None:
                continue
            if name in {"href", "src"} and not self._safe_url(value, image=name == "src"):
                continue
            rendered.append(f' {name}="{html.escape(value, quote=True)}"')
        self.output.append(f"<{tag}{''.join(rendered)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.drop_content_tags:
            self.drop_depth = max(0, self.drop_depth - 1)
            return
        if not self.drop_depth and tag in self.allowed_tags and tag not in self.void_tags:
            self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.drop_depth:
            self.output.append(html.escape(data))

    def handle_entityref(self, name: str) -> None:
        if not self.drop_depth:
            self.output.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.drop_depth:
            self.output.append(f"&#{name};")

    def result(self) -> str:
        return "".join(self.output)


def _sanitize_html(source: str) -> str:
    sanitizer = _HtmlSanitizer()
    sanitizer.feed(source)
    sanitizer.close()
    return sanitizer.result()


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
        markdown = _strip_obsidian_cover_area(_strip_obsidian_edit_panel(record["body"]))
        markdown = IMAGE_WIKILINK_PATTERN.sub(lambda match: f"![image]({match.group(1).strip()})", markdown)

        def media_url(match: re.Match[str]) -> str:
            alt, path = match.groups()
            clean_path = path.strip().strip("<>")
            if re.match(r"^(?:https?:|data:|#|/)", clean_path, flags=re.I):
                return f"![{alt}]({clean_path})"
            return f"![{alt}](/media/{quote_path(record['slug'])}/{quote_path(clean_path)})"

        markdown = MARKDOWN_IMAGE_PATTERN.sub(media_url, markdown)
        raw_html = MARKDOWN.render(markdown)
        article = {key: value for key, value in record.items() if key not in {"file", "body", "directory"}}
        article.update({"markdown": markdown, "html": _sanitize_html(raw_html)})
        return article

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


def quote_path(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


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
