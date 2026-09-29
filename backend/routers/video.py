"""Compatibility facade and aggregate router for video HTTP handlers."""
# ruff: noqa: F401

from fastapi import APIRouter

import video_runtime
from routers import video_items, video_rooms, video_streams, video_subtitles
from routers.video_items import (
    add_external_video,
    add_local_video,
    advance_video_playlist,
    delete_video_item,
    reorder_video_playlist,
    select_video_item,
    update_video_metadata,
    upload_video_item,
)
from routers.video_rooms import get_video_room, get_video_snapshot
from routers.video_streams import (
    stream_hls_resource,
    stream_video_item,
    stream_video_subtitle,
)
from routers.video_subtitles import (
    delete_video_subtitle,
    select_video_subtitle,
    upload_video_subtitle,
)

router = APIRouter(prefix="/api/video", tags=["video"])
router.include_router(video_rooms.router)
router.include_router(video_items.router)
router.include_router(video_subtitles.router)
router.include_router(video_streams.router)


def __getattr__(name):
    return getattr(video_runtime, name)


async def inspect_external_video(*args, **kwargs):
    return await video_items.inspect_external_video(*args, **kwargs)


async def open_external_stream(*args, **kwargs):
    return await video_streams.open_external_stream(*args, **kwargs)
