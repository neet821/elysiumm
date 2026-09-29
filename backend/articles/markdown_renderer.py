"""Render normalized note bodies as safe HTML and browser-ready Markdown."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any

from markdown_it import MarkdownIt

from .note_parser import (
    IMAGE_WIKILINK_PATTERN,
    MARKDOWN_IMAGE_PATTERN,
    _strip_obsidian_cover_area,
    _strip_obsidian_edit_panel,
    _strip_obsidian_metadata_match_panel,
)


MARKDOWN = MarkdownIt("commonmark", {"html": True}).enable("table")


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
        allowed_attrs = {
            "a": {"href", "name", "target", "rel"},
            "img": {"src", "alt", "title"},
            "code": {"class"},
        }
        rendered = []
        for name, value in attrs:
            name = name.lower()
            if name not in allowed_attrs.get(tag, set()) or value is None:
                continue
            if name in {"href", "src"} and not self._safe_url(
                value, image=name == "src"
            ):
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


def quote_path(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def render_article(record: dict[str, Any]) -> dict[str, Any]:
    markdown = _strip_obsidian_cover_area(
        _strip_obsidian_edit_panel(
            _strip_obsidian_metadata_match_panel(record["body"])
        )
    )
    markdown = IMAGE_WIKILINK_PATTERN.sub(
        lambda match: f"![image]({match.group(1).strip()})", markdown
    )

    def media_url(match: re.Match[str]) -> str:
        alt, path = match.groups()
        clean_path = path.strip().strip("<>")
        if re.match(r"^(?:https?:|data:|#|/)", clean_path, flags=re.I):
            return f"![{alt}]({clean_path})"
        return (
            f"![{alt}](/media/{quote_path(record['slug'])}/"
            f"{quote_path(clean_path)})"
        )

    markdown = MARKDOWN_IMAGE_PATTERN.sub(media_url, markdown)
    raw_html = MARKDOWN.render(markdown)
    article = {
        key: value
        for key, value in record.items()
        if key not in {"file", "body", "directory"}
    }
    article.update({"markdown": markdown, "html": _sanitize_html(raw_html)})
    return article
