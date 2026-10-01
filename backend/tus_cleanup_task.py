"""Periodic cleanup for abandoned tus uploads and their quota reservations."""

import asyncio
import logging

from database import SessionLocal
import tus_upload_service


logger = logging.getLogger("backend")
CLEANUP_INTERVAL_SECONDS = 15 * 60


async def run_tus_cleanup_task() -> None:
    while True:
        db = SessionLocal()
        try:
            removed = await tus_upload_service.cleanup_expired_uploads(db)
            if removed:
                logger.info("已清理 %s 个过期可续传上传", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("清理过期可续传上传失败")
        finally:
            db.close()
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
