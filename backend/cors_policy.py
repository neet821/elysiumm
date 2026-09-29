"""Shared origin configuration for the HTTP CORS middleware."""

from collections.abc import Iterable


DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:8000",
)
CODESPACES_ORIGIN_REGEX = (
    r"https://[a-zA-Z0-9\-]+\.(github\.dev|githubpreview\.dev|app\.github\.dev)$"
)


def build_cors_policy(configured_origins: Iterable[str]) -> dict[str, object]:
    """Return the exact origin options consumed by Starlette's CORS middleware."""

    return {
        "allow_origin_regex": CODESPACES_ORIGIN_REGEX,
        "allow_origins": [*DEFAULT_CORS_ORIGINS, *configured_origins],
    }
