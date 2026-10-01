from html.parser import HTMLParser
from typing import Any


class BookmarkHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.folders: list[dict[str, Any]] = []
        self.bookmarks: list[dict[str, Any]] = []
        self._folder_stack: list[str] = []
        self._dl_markers: list[bool] = []
        self._pending_folder: dict[str, Any] | None = None
        self._h3_parts: list[str] | None = None
        self._current_link: dict[str, Any] | None = None
        self._description_parts: list[str] | None = None
        self._last_bookmark: dict[str, Any] | None = None
        self._next_folder_id = 1

    def _finish_description(self) -> None:
        if self._description_parts is None or self._last_bookmark is None:
            return
        description = " ".join("".join(self._description_parts).split())
        self._last_bookmark["description"] = description or None
        self._description_parts = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attributes = dict(attrs)
        if tag in {"dt", "h3", "a", "dl"}:
            self._finish_description()
        if tag == "h3":
            self._h3_parts = []
        elif tag == "dl":
            if self._pending_folder is None:
                self._dl_markers.append(False)
            else:
                folder = self._pending_folder
                self._pending_folder = None
                self.folders.append(folder)
                self._folder_stack.append(folder["id"])
                self._dl_markers.append(True)
        elif tag == "a":
            self._current_link = {
                "url": attributes.get("href", ""),
                "title": "",
                "tags": [
                    item.strip()
                    for item in attributes.get("tags", "").split(",")
                    if item.strip()
                ],
                "folder_id": self._folder_stack[-1]
                if self._folder_stack
                else None,
            }
        elif tag == "dd":
            self._description_parts = []

    def handle_data(self, data: str) -> None:
        if self._h3_parts is not None:
            self._h3_parts.append(data)
        elif self._current_link is not None:
            self._current_link["title"] += data
        elif self._description_parts is not None:
            self._description_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "h3" and self._h3_parts is not None:
            name = " ".join("".join(self._h3_parts).split())
            key = f"html-folder-{self._next_folder_id}"
            self._next_folder_id += 1
            self._pending_folder = {
                "id": key,
                "parent_id": self._folder_stack[-1]
                if self._folder_stack
                else None,
                "name": name,
            }
            self._h3_parts = None
        elif tag == "a" and self._current_link is not None:
            self._current_link["title"] = " ".join(
                self._current_link["title"].split()
            )
            if self._current_link["url"]:
                self.bookmarks.append(self._current_link)
                self._last_bookmark = self._current_link
            self._current_link = None
        elif tag == "dd":
            self._finish_description()
        elif tag == "dl" and self._dl_markers:
            was_folder = self._dl_markers.pop()
            if was_folder and self._folder_stack:
                self._folder_stack.pop()

    def payload(self) -> dict[str, Any]:
        self._finish_description()
        return {"version": 2, "folders": self.folders, "bookmarks": self.bookmarks}
