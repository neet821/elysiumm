"""Shared server-side matching rules for Obsidian media records."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable


SEARCH_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "album": {
        "either—or": ("Either/Or", "Either Or"),
        "in rainbow": ("In Rainbows",),
        "ok computer": ("OK Computer",),
    },
    "book": {
        "奇鸟行状录": ("The Wind-Up Bird Chronicle", "The Wind Up Bird Chronicle"),
        "书上的男爵": ("The Baron in the Trees",),
        "树上的男爵": ("The Baron in the Trees",),
        "挪威的森林": ("Norwegian Wood",),
        "哈利·波特1": (
            "Harry Potter and the Philosopher's Stone",
            "Harry Potter and the Sorcerer's Stone",
        ),
        "哈利·波特2": ("Harry Potter and the Chamber of Secrets",),
        "哈利·波特": (
            "Harry Potter and the Philosopher's Stone",
            "Harry Potter and the Sorcerer's Stone",
        ),
    },
    "game": {
        "海市蜃楼之馆": ("The House in Fata Morgana",),
        "女神异闻录5": ("Persona 5", "Persona 5 Royal"),
        "极乐迪斯科": ("Disco Elysium",),
    },
    "movie": {
        "盗火线": ("Heat",),
        "诺斯费拉图": ("Nosferatu",),
        "末代皇帝": ("The Last Emperor",),
        "现代启示录": ("Apocalypse Now",),
    },
}

CREATOR_HINTS = {
    "ok computer": "Radiohead",
    "in rainbows": "Radiohead",
    "either or": "Elliott Smith",
}

GAME_NON_PRODUCT = re.compile(
    r"soundtrack|原声带|ost|demo|dlc|downloadable|supporter|升级包|音乐包|试玩版|soundtrack",
    re.IGNORECASE,
)


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text.casefold(), flags=re.UNICODE)
    return " ".join(text.split())


def search_queries(kind: str, query: str) -> list[str]:
    original = str(query or "").strip()
    aliases = SEARCH_ALIASES.get(kind, {}).get(normalize_text(original), ())
    values = [original, *aliases]
    return list(dict.fromkeys(value for value in values if value.strip()))


def _value(item: Any, key: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _creator_hint(kind: str, query: str) -> str:
    if kind != "album":
        return ""
    return normalize_text(CREATOR_HINTS.get(normalize_text(query), ""))


def _score(kind: str, query: str, candidate: Any, index: int) -> tuple[int, int]:
    title = normalize_text(_value(candidate, "title"))
    original_title = normalize_text((_value(candidate, "metadata", {}) or {}).get("original_title", ""))
    queries = [normalize_text(value) for value in search_queries(kind, query)]
    queries = [value for value in queries if value]
    best = 0
    best_query_index = len(queries)
    for query_index, search_query in enumerate(queries):
        current = 0
        if title == search_query or original_title == search_query:
            current = 1000
        elif title.startswith(search_query):
            current = 700
        elif search_query in title:
            current = 500
        elif len(title) >= 4 and title in search_query:
            current = 400
        if current > best:
            best = current
            best_query_index = query_index

    creator_hint = _creator_hint(kind, query)
    creator = normalize_text(_value(candidate, "creator"))
    if creator_hint and creator:
        if creator == creator_hint or creator_hint in creator or creator in creator_hint:
            best += 400
        else:
            best -= 1000

    # Prefer the base game over a later edition when the user's title names the base.
    if kind == "game" and best:
        candidate_title = normalize_text(_value(candidate, "title"))
        if candidate_title.endswith(" royal") and normalize_text(query) == "女神异闻录5":
            best -= 5

    # Earlier aliases are deliberate: the base title precedes editions and spin-offs.
    return best, best_query_index * -1 - index


def rank_candidates(
    kind: str,
    query: str,
    candidates: Iterable[Any],
) -> tuple[list[Any], Any | None]:
    scored: list[tuple[int, int, int, Any]] = []
    for index, candidate in enumerate(candidates):
        title = str(_value(candidate, "title") or _value(candidate, "name") or "").strip()
        if not title:
            continue
        if kind == "game" and GAME_NON_PRODUCT.search(title):
            continue
        score, tie_break = _score(kind, query, candidate, index)
        scored.append((score, tie_break, index, candidate))
    scored.sort(key=lambda row: (-row[0], -row[1], row[2]))
    ranked = [row[3] for row in scored]
    recommendation = None
    if scored and scored[0][0] >= 700:
        top_score = scored[0][0]
        if sum(1 for row in scored if row[0] == top_score) == 1:
            recommendation = scored[0][3]
    return ranked, recommendation
