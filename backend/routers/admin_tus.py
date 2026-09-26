"""管理员专属 tus 上传代理。浏览器永远不直接访问 tusd。"""

import base64
import binascii
import json
import re
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

import models
import tus_upload_service
from database import get_db
from dependencies import get_current_admin


router = APIRouter(prefix="/api/admin/tus", tags=["admin-tus"])
UPLOAD_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
TUS_VERSION = "1.0.0"
_CREATE_HEADERS = ("Tus-Resumable", "Upload-Length", "Upload-Metadata")
_PATCH_HEADERS = (
    "Tus-Resumable",
    "Upload-Offset",
    "Content-Type",
    "Content-Length",
)


def require_tus_admin(
    current_admin: models.User = Depends(get_current_admin),
) -> models.User:
    if not tus_upload_service.config.TUS_UPLOADS_ENABLED:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "本地预览中的可续传上传服务未启动",
        )
    return current_admin
_RESPONSE_HEADERS = (
    "Tus-Resumable",
    "Tus-Version",
    "Tus-Extension",
    "Tus-Max-Size",
    "Upload-Offset",
    "Upload-Length",
    "Upload-Metadata",
    "Cache-Control",
    "Content-Type",
)


def parse_upload_metadata(value: str | None) -> dict[str, str]:
    if not value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "缺少 Upload-Metadata")

    metadata: dict[str, str] = {}
    try:
        for entry in value.split(","):
            parts = entry.strip().split(" ", 1)
            if len(parts) != 2 or not parts[0] or parts[0] in metadata:
                raise ValueError("invalid metadata entry")
            key, encoded = parts
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            metadata[key] = decoded
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Upload-Metadata 格式无效"
        ) from exc

    required = {"filename", "purpose"}
    if not required.issubset(metadata):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "上传元数据不完整")
    if set(metadata) - {"filename", "filetype", "purpose", "session_id"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "上传元数据包含未知字段")
    if metadata["purpose"] not in {"admin_file", "transfer_file"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "上传用途无效")
    return metadata


def _upload_id_from_location(location: str | None) -> str:
    if not location:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "上传服务未返回上传地址")
    parsed = urlsplit(location)
    internal = urlsplit(tus_upload_service.tusd_url())
    if parsed.netloc and (parsed.scheme, parsed.netloc) != (internal.scheme, internal.netloc):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "上传服务返回了无效地址")
    expected_prefix = internal.path.rstrip("/") + "/"
    if not parsed.path.startswith(expected_prefix):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "上传服务返回了无效地址")
    upload_id = parsed.path[len(expected_prefix) :].strip("/")
    if not UPLOAD_ID_PATTERN.fullmatch(upload_id):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "上传服务返回了无效 ID")
    return upload_id


def _public_response_headers(upstream: httpx.Response, upload_id: str | None = None) -> dict[str, str]:
    headers = {
        name: value
        for name in _RESPONSE_HEADERS
        if (value := upstream.headers.get(name)) is not None
    }
    location = upstream.headers.get("Location")
    if location and upload_id:
        headers["Location"] = f"/api/admin/tus/{upload_id}"
    if upstream.status_code == status.HTTP_204_NO_CONTENT:
        headers.pop("Content-Type", None)
    return headers


async def _send_upstream(
    request: Request,
    method: str,
    url: str,
    headers: dict[str, str],
):
    client = tus_upload_service.create_tusd_client()
    content = request.stream() if method == "PATCH" else None
    upstream = None
    try:
        upstream_request = client.build_request(
            method,
            url,
            headers=headers,
            content=content,
        )
        upstream = await client.send(upstream_request, stream=True)
        await upstream.aread()
        return upstream
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "可续传上传服务暂不可用"
        ) from exc
    finally:
        if upstream is not None:
            await upstream.aclose()
        await client.aclose()


def _response(upstream: httpx.Response, upload_id: str | None = None) -> Response:
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_public_response_headers(upstream, upload_id),
    )


@router.options("/")
async def tus_capabilities(
    request: Request,
    _current_admin: models.User = Depends(require_tus_admin),
):
    upstream = await _send_upstream(
        request,
        "OPTIONS",
        tus_upload_service.tusd_url(),
        {},
    )
    return _response(upstream)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_upload(
    request: Request,
    current_admin: models.User = Depends(require_tus_admin),
    db: Session = Depends(get_db),
):
    if request.headers.get("Tus-Resumable") != TUS_VERSION:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "不支持的 tus 协议版本")
    raw_length = request.headers.get("Upload-Length")
    if not raw_length or not raw_length.isdecimal():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload-Length 格式无效")
    if not request.headers.get("Upload-Metadata"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "缺少 Upload-Metadata")
    metadata = parse_upload_metadata(request.headers.get("Upload-Metadata"))
    reservation = tus_upload_service.reserve_upload(
        db,
        owner=current_admin,
        filename=metadata["filename"],
        content_type=metadata.get("filetype"),
        purpose=metadata["purpose"],
        upload_length=int(raw_length),
        session_id=metadata.get("session_id"),
    )

    headers = {
        name: value
        for name in _CREATE_HEADERS
        if (value := request.headers.get(name)) is not None
    }
    try:
        upstream = await _send_upstream(
            request,
            "POST",
            tus_upload_service.tusd_url(),
            headers,
        )
        if upstream.status_code != status.HTTP_201_CREATED:
            reservation.status = "failed"
            reservation.failure_code = "tusd_create_rejected"
            db.commit()
            return Response(
                content="上传服务拒绝创建任务",
                status_code=status.HTTP_502_BAD_GATEWAY,
                media_type="text/plain; charset=utf-8",
            )
        upload_id = _upload_id_from_location(upstream.headers.get("Location"))
        reservation.upload_id = upload_id
        reservation.status = "active"
        reservation.last_activity_at = tus_upload_service.utcnow()
        reservation.expires_at = reservation.last_activity_at + timedelta(
            seconds=tus_upload_service.config.TUS_UPLOAD_TTL_SECONDS
        )
        db.commit()
        return _response(upstream, upload_id)
    except HTTPException:
        reservation.status = "failed"
        reservation.failure_code = "tusd_create_failed"
        db.commit()
        raise


@router.head("/{upload_id}")
async def head_upload(
    upload_id: str,
    request: Request,
    _current_admin: models.User = Depends(require_tus_admin),
    db: Session = Depends(get_db),
):
    reservation = tus_upload_service.reservation_for_owner(db, upload_id, _current_admin)
    if request.headers.get("Tus-Resumable") != TUS_VERSION:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "不支持的 tus 协议版本")
    if reservation.status == "complete":
        return Response(
            status_code=status.HTTP_200_OK,
            headers={
                "Tus-Resumable": TUS_VERSION,
                "Upload-Length": str(reservation.upload_length),
                "Upload-Offset": str(reservation.upload_length),
                "Cache-Control": "no-store",
            },
        )
    upstream = await _send_upstream(
        request,
        "HEAD",
        tus_upload_service.tusd_url(upload_id),
        {"Tus-Resumable": TUS_VERSION},
    )
    offset = upstream.headers.get("Upload-Offset")
    length = upstream.headers.get("Upload-Length")
    if upstream.status_code == status.HTTP_200_OK and offset and length:
        if (
            not offset.isdecimal()
            or not length.isdecimal()
            or int(length) != reservation.upload_length
            or int(offset) > reservation.upload_length
        ):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "上传服务状态不一致")
        reservation.upload_offset = int(offset)
        reservation.last_activity_at = tus_upload_service.utcnow()
        reservation.expires_at = reservation.last_activity_at + timedelta(
            seconds=tus_upload_service.config.TUS_UPLOAD_TTL_SECONDS
        )
        tus_upload_service.refresh_transfer_session(db, reservation)
        db.commit()
        if reservation.upload_offset == reservation.upload_length:
            tus_upload_service.finalize_upload(db, reservation=reservation)
    return _response(upstream, upload_id)


@router.options("/{upload_id}")
async def upload_capabilities(
    upload_id: str,
    request: Request,
    _current_admin: models.User = Depends(require_tus_admin),
    db: Session = Depends(get_db),
):
    tus_upload_service.reservation_for_owner(db, upload_id, _current_admin)
    upstream = await _send_upstream(
        request,
        "OPTIONS",
        tus_upload_service.tusd_url(upload_id),
        {},
    )
    return _response(upstream, upload_id)


@router.patch("/{upload_id}")
async def patch_upload(
    upload_id: str,
    request: Request,
    _current_admin: models.User = Depends(require_tus_admin),
    db: Session = Depends(get_db),
):
    reservation = tus_upload_service.reservation_for_owner(db, upload_id, _current_admin)
    if request.headers.get("Tus-Resumable") != TUS_VERSION:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "不支持的 tus 协议版本")
    if reservation.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "上传当前不可续传")
    if request.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/offset+octet-stream":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "上传分块类型无效")
    raw_offset = request.headers.get("Upload-Offset", "")
    if not raw_offset.isdecimal() or int(raw_offset) != reservation.upload_offset:
        raise HTTPException(status.HTTP_409_CONFLICT, "上传偏移已变化，请先检查续传状态")
    headers = {
        name: value
        for name in _PATCH_HEADERS
        if (value := request.headers.get(name)) is not None
    }
    upstream = await _send_upstream(
        request,
        "PATCH",
        tus_upload_service.tusd_url(upload_id),
        headers,
    )
    if upstream.status_code == status.HTTP_204_NO_CONTENT:
        new_offset = upstream.headers.get("Upload-Offset", "")
        if (
            not new_offset.isdecimal()
            or int(new_offset) < reservation.upload_offset
            or int(new_offset) > reservation.upload_length
        ):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "上传服务返回了无效偏移")
        reservation.upload_offset = int(new_offset)
        reservation.last_activity_at = tus_upload_service.utcnow()
        reservation.expires_at = reservation.last_activity_at + timedelta(
            seconds=tus_upload_service.config.TUS_UPLOAD_TTL_SECONDS
        )
        tus_upload_service.refresh_transfer_session(db, reservation)
        db.commit()
        if reservation.upload_offset == reservation.upload_length:
            tus_upload_service.finalize_upload(db, reservation=reservation)
    return _response(upstream, upload_id)


@router.delete("/{upload_id}")
async def cancel_upload(
    upload_id: str,
    request: Request,
    _current_admin: models.User = Depends(require_tus_admin),
    db: Session = Depends(get_db),
):
    reservation = tus_upload_service.reservation_for_owner(
        db,
        upload_id,
        _current_admin,
        allowed_statuses=("creating", "active", "complete", "cancelled"),
    )
    if reservation.status == "cancelled":
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if reservation.status == "complete":
        raise HTTPException(status.HTTP_409_CONFLICT, "已完成的上传不能取消")
    if request.headers.get("Tus-Resumable") != TUS_VERSION:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "不支持的 tus 协议版本")
    upstream = await _send_upstream(
        request,
        "DELETE",
        tus_upload_service.tusd_url(upload_id),
        {"Tus-Resumable": TUS_VERSION},
    )
    if upstream.status_code in {status.HTTP_204_NO_CONTENT, status.HTTP_404_NOT_FOUND}:
        reservation.status = "cancelled"
        reservation.last_activity_at = tus_upload_service.utcnow()
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return _response(upstream, upload_id)


@router.get("/{upload_id}/result")
def get_upload_result(
    upload_id: str,
    _current_admin: models.User = Depends(require_tus_admin),
    db: Session = Depends(get_db),
):
    reservation = tus_upload_service.reservation_for_owner(db, upload_id, _current_admin)
    if reservation.status != "complete" or not reservation.result_payload:
        raise HTTPException(status.HTTP_409_CONFLICT, "上传尚未完成")
    return json.loads(reservation.result_payload)
