"""tus 协议头、元数据校验和内部 tusd 代理适配。"""

import base64
import binascii
import re
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException, Request, Response, status

import tus_upload_service


UPLOAD_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
TUS_VERSION = "1.0.0"
_CREATE_HEADERS = ("Tus-Resumable", "Upload-Length", "Upload-Metadata")
_PATCH_HEADERS = (
    "Tus-Resumable",
    "Upload-Offset",
    "Content-Type",
    "Content-Length",
)
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


def _public_response_headers(
    upstream: httpx.Response,
    upload_id: str | None = None,
) -> dict[str, str]:
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
