"""Authorize and proxy HLS playlists and their nested media resources."""

from datetime import timedelta

from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

import models
import security
import sync_room_crud
from external_media import rewrite_hls_playlist


MAX_HLS_PLAYLIST_SIZE = 2 * 1024 * 1024


def _hls_resource_token(item_id, user_id, target_url):
    return security.create_token(
        {
            "resource": "video_hls",
            "resource_id": item_id,
            "user_id": user_id,
            "target_url": target_url,
        },
        timedelta(hours=6),
        token_type="hls_resource",
    )


def _hls_resource_url(item_id, user_id, target_url):
    return f"/api/video/items/{item_id}/hls?resource={_hls_resource_token(item_id, user_id, target_url)}"


def _authorized_hls_resource(db, item_id, token):
    payload = security.decode_token_payload(token)
    if (
        payload.get("type") != "hls_resource"
        or payload.get("resource") != "video_hls"
        or payload.get("resource_id") != item_id
        or not isinstance(payload.get("user_id"), int)
        or not isinstance(payload.get("target_url"), str)
    ):
        raise HTTPException(401, "HLS 访问凭据无效")
    user, item = (
        db.get(models.User, payload["user_id"]),
        db.get(models.VideoPlaylistItem, item_id),
    )
    if user is None or item is None or item.source_type != "external":
        raise HTTPException(404, "视频不存在")
    if not user.is_active:
        raise HTTPException(403, "账号已停用")
    if not sync_room_crud.is_room_member(db, item.room_id, user.id):
        raise HTTPException(403, "请先加入视频房")
    return user, item, payload["target_url"]


async def _read_remote_limited(remote, maximum=MAX_HLS_PLAYLIST_SIZE):
    output = bytearray()
    try:
        async for chunk in remote.aiter_bytes():
            output.extend(chunk)
            if len(output) > maximum:
                raise HTTPException(413, "HLS 清单过大")
        return bytes(output)
    finally:
        await remote.aclose()


def _remote_streaming_response(remote):
    async def body():
        try:
            async for chunk in remote.aiter_bytes():
                yield chunk
        finally:
            await remote.aclose()

    headers = {
        target: value
        for source, target in (
            ("accept-ranges", "Accept-Ranges"),
            ("content-length", "Content-Length"),
            ("content-range", "Content-Range"),
        )
        if (value := remote.headers.get(source))
    }
    return StreamingResponse(
        body(),
        status_code=remote.status_code,
        media_type=remote.headers.get("content-type", "application/octet-stream").split(
            ";", 1
        )[0],
        headers=headers,
    )


async def _hls_playlist_response(remote, item, user):
    raw = await _read_remote_limited(remote)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(415, "HLS 清单不是有效的 UTF-8 文本") from exc
    if not text.lstrip().startswith("#EXTM3U"):
        raise HTTPException(415, "HLS 清单缺少有效文件头")
    return Response(
        rewrite_hls_playlist(
            text, remote.url, lambda target: _hls_resource_url(item.id, user.id, target)
        ),
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-store"},
    )
