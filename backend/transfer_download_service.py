import mimetypes
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import models
import transfer_service


def create_transfer_download_response(
    db: Session,
    session: models.TransferSession,
    item: models.TransferFile,
    request: Request,
) -> StreamingResponse:
    path = Path(item.storage_path).resolve()
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文件已清理")

    size = path.stat().st_size
    start = 0
    end = size - 1
    range_header = request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        start_text, _, end_text = range_header[6:].partition("-")
        start = int(start_text or 0)
        end = min(int(end_text) if end_text else size - 1, size - 1)
        if start > end or start >= size:
            raise HTTPException(
                status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                "无效的 Range",
            )

    transfer_service.refresh_expiry(session)
    db.commit()
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Content-Disposition": (
            f"attachment; filename*=UTF-8''{quote(item.original_name)}"
        ),
        "Content-Type": (
            mimetypes.guess_type(item.original_name)[0]
            or "application/octet-stream"
        ),
    }
    if range_header:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        iter_file(path, start, end),
        status_code=206 if range_header else 200,
        headers=headers,
    )


def iter_file(path: Path, start: int, end: int, chunk_size: int = 1024 * 1024):
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
