from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from .store import ArticleForbiddenError, ArticleNotFoundError, ArticleStore, CATEGORY_LABELS, media_type_for


router = APIRouter()


def _raw_suffix(request: Request, prefix: str) -> str:
    raw_path = request.scope.get("raw_path")
    prefix_bytes = prefix.encode("ascii")
    if isinstance(raw_path, bytes) and raw_path.startswith(prefix_bytes):
        return raw_path[len(prefix_bytes) :].decode("ascii")
    return request.url.path.removeprefix(prefix)


def _not_found() -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "not_found"})


@router.get("/api/articles")
def list_articles():
    return {"articles": ArticleStore.from_environment().list_articles()}


@router.get("/api/content")
def list_content():
    items = ArticleStore.from_environment().list_articles()
    categories = [
        {"id": content_type, "label": label, "items": [item for item in items if item["contentType"] == content_type]}
        for content_type, label in CATEGORY_LABELS.items()
    ]
    return {"categories": categories, "items": items}


@router.get("/api/content/{content_type}/{slug:path}")
def get_content(content_type: str, slug: str):
    if content_type not in CATEGORY_LABELS or not slug:
        return _not_found()
    try:
        article = ArticleStore.from_environment().get_article(slug)
    except ArticleNotFoundError:
        return _not_found()
    if article["contentType"] != content_type:
        return _not_found()
    return {"article": article, "html": article["html"]}


@router.get("/api/articles/{slug:path}")
def get_article(request: Request, slug: str):
    del slug
    try:
        article = ArticleStore.from_environment().get_article(unquote(_raw_suffix(request, "/api/articles/")))
    except ArticleNotFoundError:
        return _not_found()
    return {"article": article, "html": article["html"]}


@router.get("/media/{remainder:path}")
def get_media(request: Request, remainder: str):
    del remainder
    encoded_slug, separator, encoded_media_path = _raw_suffix(request, "/media/").partition("/")
    if not separator or not encoded_slug:
        return _not_found()
    try:
        path = ArticleStore.from_environment().resolve_media(unquote(encoded_slug), encoded_media_path)
    except ArticleNotFoundError:
        return _not_found()
    except ArticleForbiddenError:
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    return FileResponse(path, media_type=media_type_for(path), headers={"cache-control": "public, max-age=300"})
