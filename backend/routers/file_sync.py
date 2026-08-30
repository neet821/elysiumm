from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import quote, unquote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from file_sync_paths import relative_item_path
import models
from dependencies import get_current_user


router = APIRouter(prefix="/api/admin/file-sync", tags=["file-sync"])


class DirectoryParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.items = []; self._href = None

    def handle_starttag(self, tag, attrs):
        if tag == "a": self._href = dict(attrs).get("href")

    def handle_data(self, data):
        if self._href is not None:
            href = unquote(self._href)
            if href not in {"../", "./"} and not href.startswith("http"):
                path = href.strip("/")
                if href.endswith("/"):
                    path += "/"
                self.items.append({"name": data.strip() or path.strip("/"), "path": path})

    def handle_endtag(self, tag):
        if tag == "a": self._href = None


def admin_user(user: models.User = Depends(get_current_user)):
    if user.role != "admin" or not user.is_active: raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


def base_url() -> str:
    return os.getenv("PUBLIC_FRP_FILE_URL", "http://127.0.0.1:6001/files").rstrip("/")


def auth() -> tuple[str, str] | None:
    username = os.getenv("PUBLIC_FRP_FILE_USERNAME", "").strip(); password = os.getenv("PUBLIC_FRP_FILE_PASSWORD", "")
    return (username, password) if username and password else None


def safe_path(value: str) -> str:
    decoded = unquote(value or "").replace("\\", "/").strip("/")
    path = PurePosixPath(decoded)
    if not decoded or any(part in {"", ".", ".."} for part in path.parts) or path.is_absolute(): raise HTTPException(status.HTTP_400_BAD_REQUEST, "路径无效")
    return "/".join(path.parts)


async def fetch(path: str = ""):
    credentials = auth()
    if not credentials: raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "文件同步尚未配置鉴权")
    try:
        client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=30.0), auth=credentials, follow_redirects=False)
        response = await client.get(f"{base_url()}/{quote(path, safe='/')}")
        return client, response
    except httpx.HTTPError as exc: raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "文件同步离线") from exc


@router.get("/status")
async def sync_status(_admin: models.User = Depends(admin_user)):
    client, response = await fetch()
    await client.aclose()
    if response.status_code == 401: return {"status": "auth_failed"}
    if response.status_code >= 400: return {"status": "offline", "http_status": response.status_code}
    return {"status": "online"}


@router.get("/browse")
async def browse(path: str = "", _admin: models.User = Depends(admin_user)):
    normalized = safe_path(path) if path else ""
    client, response = await fetch(normalized)
    await client.aclose()
    if response.status_code == 401: raise HTTPException(status.HTTP_502_BAD_GATEWAY, "文件同步鉴权失败")
    if response.status_code >= 400: raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "文件同步目录暂时不可用")
    parser = DirectoryParser(); parser.feed(response.text)
    items = [{**item, "path": relative_item_path(item["path"], normalized, base_url())} for item in parser.items]
    return {"status": "online", "path": normalized, "items": [item for item in items if item["path"]]}


@router.get("/download")
async def download(path: str, _admin: models.User = Depends(admin_user)):
    normalized = safe_path(path)
    credentials = auth()
    try:
        client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=60.0), auth=credentials, follow_redirects=False)
        upstream = await client.send(client.build_request("GET", f"{base_url()}/{quote(normalized, safe='/')}"), stream=True)
        if upstream.status_code == 401:
            await upstream.aclose(); await client.aclose(); raise HTTPException(status.HTTP_502_BAD_GATEWAY, "文件同步鉴权失败")
        if upstream.status_code >= 400:
            await upstream.aclose(); await client.aclose(); raise HTTPException(status.HTTP_404_NOT_FOUND, "文件不存在")
        headers = {key: value for key, value in upstream.headers.items() if key.lower() in {"content-length", "content-type", "last-modified", "etag"}}
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(normalized.rsplit('/', 1)[-1])}"
        async def body():
            try:
                async for chunk in upstream.aiter_bytes(): yield chunk
            finally:
                await upstream.aclose(); await client.aclose()
        return StreamingResponse(body(), headers=headers)
    except httpx.HTTPError as exc: await client.aclose(); raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "文件同步离线") from exc
