from datetime import datetime
from html import escape
from typing import Any

from sqlalchemy.orm import Session

import models
from bookmark_search_service import search_bookmarks
from bookmark_tag_service import tags_for_bookmark


def export_bookmarks_json(
    db: Session,
    user_id: int,
    *,
    record_job: bool = True,
) -> dict[str, Any]:
    folders = (
        db.query(models.BookmarkFolder)
        .filter(models.BookmarkFolder.user_id == user_id)
        .order_by(models.BookmarkFolder.sort_order, models.BookmarkFolder.id)
        .all()
    )
    bookmarks = search_bookmarks(db, user_id)

    if record_job:
        db.add(
            models.BookmarkExportJob(
                user_id=user_id,
                status="completed",
                export_type="json",
                exported_count=len(bookmarks),
                finished_at=datetime.utcnow(),
            )
        )
        db.commit()

    return {
        "version": 2,
        "folders": [
            {
                "id": folder.id,
                "parent_id": folder.parent_id,
                "name": folder.name,
                "icon": folder.icon,
                "color": folder.color,
                "sort_order": folder.sort_order,
                "is_sensitive": folder.is_sensitive,
                "is_public": folder.is_public,
            }
            for folder in folders
        ],
        "bookmarks": [
            {
                "id": bookmark.id,
                "folder_id": bookmark.folder_id,
                "title": bookmark.title,
                "url": bookmark.url,
                "description": bookmark.description,
                "favicon": bookmark.favicon,
                "preview_url": bookmark.preview_url,
                "sort_order": bookmark.sort_order,
                "is_public": bookmark.is_public,
                "is_pinned": bookmark.is_pinned,
                "show_description": bookmark.show_description,
                "show_preview": bookmark.show_preview,
                "show_visit_count": bookmark.show_visit_count,
                "allow_indexing": bookmark.allow_indexing,
                "visit_count": bookmark.visit_count,
                "last_visited_at": (
                    bookmark.last_visited_at.isoformat()
                    if bookmark.last_visited_at
                    else None
                ),
                "tags": tags_for_bookmark(bookmark),
            }
            for bookmark in bookmarks
        ],
    }


def _html_bookmark_lines(item: dict[str, Any], indent: str) -> list[str]:
    tags = ",".join(item.get("tags") or [])
    lines = [
        (
            f'{indent}<DT><A HREF="{escape(item["url"], quote=True)}" '
            f'TAGS="{escape(tags, quote=True)}">{escape(item["title"])}</A>'
        )
    ]
    if item.get("description"):
        lines.append(f'{indent}<DD>{escape(item["description"])}')
    return lines


def export_bookmarks_html(db: Session, user_id: int) -> str:
    payload = export_bookmarks_json(db, user_id)
    folder_by_id = {item["id"]: item for item in payload["folders"]}
    children: dict[int | None, list[dict[str, Any]]] = {}
    for folder in payload["folders"]:
        parent_id = folder.get("parent_id")
        if parent_id not in folder_by_id:
            parent_id = None
        children.setdefault(parent_id, []).append(folder)
    bookmarks_by_folder: dict[int | None, list[dict[str, Any]]] = {}
    for bookmark in payload["bookmarks"]:
        folder_id = bookmark.get("folder_id")
        if folder_id not in folder_by_id:
            folder_id = None
        bookmarks_by_folder.setdefault(folder_id, []).append(bookmark)

    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]
    for bookmark in bookmarks_by_folder.get(None, []):
        lines.extend(_html_bookmark_lines(bookmark, "  "))

    visited: set[int] = set()

    def render_folder(folder: dict[str, Any], indent: str) -> None:
        folder_id = folder["id"]
        if folder_id in visited:
            return
        visited.add(folder_id)
        lines.append(f'{indent}<DT><H3>{escape(folder["name"])}</H3>')
        lines.append(f"{indent}<DL><p>")
        for bookmark in bookmarks_by_folder.get(folder_id, []):
            lines.extend(_html_bookmark_lines(bookmark, f"{indent}  "))
        for child in children.get(folder_id, []):
            render_folder(child, f"{indent}  ")
        lines.append(f"{indent}</DL><p>")

    for root in children.get(None, []):
        render_folder(root, "  ")
    lines.append("</DL><p>")
    return "\n".join(lines)
