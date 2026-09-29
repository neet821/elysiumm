"""Persist validated bookmark import plans and report their outcomes."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

import models
from bookmark_import.errors import BookmarkImportValidationError
from bookmark_import.plan import _BookmarkImportPlan, _ImportBookmark, _ImportFolder
from bookmark_tag_service import get_or_create_tag


class BookmarkImportExecutionError(RuntimeError):
    pass


def _import_report(
    plan: _BookmarkImportPlan,
    *,
    source_type: str,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "dry_run": dry_run,
        "folder_count": len(plan.folders),
        "bookmark_count": plan.bookmark_count,
        "importable_count": len(plan.bookmarks),
        "duplicate_count": plan.duplicate_count,
        "skipped_count": plan.duplicate_count,
    }


def serialize_import_job(job: models.BookmarkImportJob) -> dict[str, Any]:
    report = None
    if job.report_json:
        try:
            report = json.loads(job.report_json)
        except (TypeError, json.JSONDecodeError):
            report = None
    return {
        "id": job.id,
        "user_id": job.user_id,
        "status": job.status,
        "source_type": job.source_type,
        "imported_count": job.imported_count,
        "folder_count": job.folder_count,
        "skipped_count": job.skipped_count,
        "duplicate_count": job.duplicate_count,
        "dry_run": job.dry_run,
        "backup_id": job.backup_id,
        "report": report,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }


def _insert_import_folder(
    db: Session,
    user_id: int,
    folder: _ImportFolder,
    parent_id: int | None,
) -> models.BookmarkFolder:
    record = models.BookmarkFolder(
        user_id=user_id,
        parent_id=parent_id,
        name=folder.name,
        icon=folder.icon,
        color=folder.color,
        sort_order=folder.sort_order,
        is_sensitive=folder.is_sensitive,
        is_public=folder.is_public,
    )
    db.add(record)
    db.flush()
    return record


def _insert_import_bookmark(
    db: Session,
    user_id: int,
    bookmark: _ImportBookmark,
    folder_id: int | None,
) -> models.Bookmark:
    record = models.Bookmark(
        user_id=user_id,
        folder_id=folder_id,
        title=bookmark.title,
        url=bookmark.url,
        description=bookmark.description,
        favicon=bookmark.favicon,
        preview_url=bookmark.preview_url,
        sort_order=bookmark.sort_order,
        is_public=bookmark.is_public,
        is_pinned=bookmark.is_pinned,
        visit_count=bookmark.visit_count,
        show_description=bookmark.show_description,
        show_preview=bookmark.show_preview,
        show_visit_count=bookmark.show_visit_count,
        allow_indexing=bookmark.allow_indexing,
        last_visited_at=bookmark.last_visited_at,
    )
    db.add(record)
    db.flush()
    for tag_name in bookmark.tags:
        tag = get_or_create_tag(db, user_id, tag_name)
        db.add(
            models.BookmarkTagRelation(
                bookmark_id=record.id,
                tag_id=tag.id,
            )
        )
    return record


def _clear_user_collection_for_restore(db: Session, user_id: int) -> None:
    bookmark_ids = [
        row[0]
        for row in db.query(models.Bookmark.id)
        .filter(models.Bookmark.user_id == user_id)
        .all()
    ]
    for instance in list(db.identity_map.values()):
        owned = (
            isinstance(instance, models.Bookmark)
            and instance.user_id == user_id
        ) or (
            isinstance(instance, models.BookmarkFolder)
            and instance.user_id == user_id
        ) or (
            isinstance(instance, models.BookmarkTag)
            and instance.user_id == user_id
        ) or (
            isinstance(instance, models.BookmarkTagRelation)
            and instance.bookmark_id in bookmark_ids
        )
        if owned:
            db.expunge(instance)
    if bookmark_ids:
        db.query(models.BookmarkTagRelation).filter(
            models.BookmarkTagRelation.bookmark_id.in_(bookmark_ids)
        ).delete(synchronize_session=False)
        db.query(models.Bookmark).filter(
            models.Bookmark.user_id == user_id
        ).delete(synchronize_session=False)
    db.query(models.BookmarkFolder).filter(
        models.BookmarkFolder.user_id == user_id
    ).update({"parent_id": None}, synchronize_session=False)
    db.query(models.BookmarkFolder).filter(
        models.BookmarkFolder.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(models.BookmarkTag).filter(
        models.BookmarkTag.user_id == user_id
    ).delete(synchronize_session=False)


def _execute_import_plan(
    db: Session,
    user_id: int,
    plan: _BookmarkImportPlan,
    *,
    source_type: str,
    dry_run: bool,
    backup_dir: Path | None,
    replace_existing: bool,
) -> models.BookmarkImportJob:
    from bookmark_backup_service import (
        BookmarkBackupValidationError,
        bookmark_backup_output_dir,
        create_bookmark_backup,
    )

    report = _import_report(plan, source_type=source_type, dry_run=dry_run)
    if dry_run:
        job = models.BookmarkImportJob(
            user_id=user_id,
            status="completed",
            source_type=source_type,
            imported_count=0,
            folder_count=len(plan.folders),
            skipped_count=plan.duplicate_count,
            duplicate_count=plan.duplicate_count,
            dry_run=True,
            report_json=json.dumps(report, ensure_ascii=False),
            finished_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    try:
        backup = create_bookmark_backup(
            db,
            user_id,
            backup_dir or bookmark_backup_output_dir(),
        )
    except BookmarkBackupValidationError as exc:
        raise BookmarkImportValidationError(
            "当前收藏无法安全备份"
        ) from exc
    job = models.BookmarkImportJob(
        user_id=user_id,
        status="running",
        source_type=source_type,
        folder_count=len(plan.folders),
        skipped_count=plan.duplicate_count,
        duplicate_count=plan.duplicate_count,
        dry_run=False,
        backup_id=backup.id,
        report_json=json.dumps(report, ensure_ascii=False),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id

    try:
        if replace_existing:
            _clear_user_collection_for_restore(db, user_id)

        folder_id_map: dict[str, int] = {}
        for folder in plan.folders:
            parent_id = (
                folder_id_map[folder.parent_key]
                if folder.parent_key is not None
                else None
            )
            record = _insert_import_folder(db, user_id, folder, parent_id)
            folder_id_map[folder.key] = record.id
        for bookmark in plan.bookmarks:
            folder_id = (
                folder_id_map[bookmark.folder_key]
                if bookmark.folder_key is not None
                else None
            )
            _insert_import_bookmark(db, user_id, bookmark, folder_id)

        active_job = db.get(models.BookmarkImportJob, job_id)
        active_job.status = "completed"
        active_job.imported_count = len(plan.bookmarks)
        active_job.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(active_job)
        return active_job
    except Exception as exc:
        db.rollback()
        failed_job = db.get(models.BookmarkImportJob, job_id)
        failed_job.status = "failed"
        failed_job.error_message = "Import failed and all changes were rolled back"
        failed_job.finished_at = datetime.utcnow()
        db.commit()
        raise BookmarkImportExecutionError(
            "收藏导入失败，已回滚"
        ) from exc
