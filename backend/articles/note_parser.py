"""Parse Obsidian Markdown notes into normalized content metadata."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


CATEGORY_LABELS = {"article": "文章", "essay": "随笔", "photo": "照片", "record": "记录"}
FRONTMATTER_KEYS = ("cover", "image", "thumbnail")
EXCERPT_KEYS = ("description", "excerpt", "summary", "preview")
COVER_AREA_PATTERN = re.compile(
    r"<!--\s*elysium-cover:start\s*-->[\s\S]*?<!--\s*elysium-cover:end\s*-->",
    re.I,
)
EDIT_INFO_CALLOUT_PATTERN = re.compile(
    r"^\s*>\s*\[!info\]-\s*编辑信息\s*\n(?:(?:^\s*>.*(?:\n|$))|^\s*\n)*",
    re.I | re.M,
)
IMAGE_WIKILINK_PATTERN = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
TITLE_FOLLOWED_YAML_PATTERN = re.compile(
    r"^\s*#\s+(.+?)\s*\n+\s*\n((?:[A-Za-z_][\w-]*\s*:\s*.*\n?)+)\s*\n",
    re.M,
)


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


def _strip_obsidian_metadata_match_panel(source: str) -> str:
    return re.sub(
        r"<!--\s*elysium-metadata-match:start\s*-->[\s\S]*?<!--\s*elysium-metadata-match:end\s*-->",
        "",
        source,
        flags=re.I,
    )


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

    return re.sub(
        r"^\s*##\s+封面\s*$",
        "",
        COVER_AREA_PATTERN.sub(replace, source),
        flags=re.I | re.M,
    )


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


def _parse_note(
    source: str, fallback_title: str
) -> tuple[dict[str, Any], str, str, str, str]:
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
    title = (
        _clean_text(data.get("title"))
        or _first_heading(source)
        or fallback_title
        or "Untitled"
    )
    cover_area = COVER_AREA_PATTERN.search(body)
    cover = _first_image_reference(cover_area.group(0)) if cover_area else ""
    if not cover:
        cover = next(
            (
                _media_reference(data.get(key))
                for key in FRONTMATTER_KEYS
                if _media_reference(data.get(key))
            ),
            "",
        )
    excerpt_key = next((key for key in EXCERPT_KEYS if key in data), None)
    if excerpt_key:
        excerpt = _clean_text(data[excerpt_key])
    else:
        excerpt_body = _strip_obsidian_cover_area(_strip_obsidian_edit_panel(body))
        excerpt_body = re.sub(r"^---[\s\S]*?---\s*", "", excerpt_body, flags=re.M)
        excerpt_body = re.sub(r"^\s*#.*$", "", excerpt_body, flags=re.M)
        excerpt_body = re.sub(r"!\[\[.*?\]\]", "", excerpt_body)
        excerpt_body = re.sub(r"[#>*_`\[\]]", "", excerpt_body)
        excerpt = next(
            (part.strip() for part in re.split(r"\n\s*\n", excerpt_body) if part.strip()),
            "",
        )
    return data, body, title, cover, re.sub(r"\s+", " ", excerpt).strip()[:280]


def _classify(relative_path: str, data: dict[str, Any]) -> tuple[str, str] | None:
    parts = [part.lower() for part in Path(relative_path).parts]
    if _is_template_path(relative_path):
        return None
    raw_type = _clean_text(
        data.get("type") or data.get("kind") or data.get("content_type")
    ).lower()
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
