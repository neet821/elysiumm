import hashlib
import shutil
from datetime import datetime
from pathlib import Path

import models


class UnsafeRecordingPath(ValueError):
    pass


def _managed_file(recording_root: Path, candidate_path: Path) -> Path:
    root = Path(recording_root).expanduser().resolve()
    candidate = Path(candidate_path).expanduser().resolve()
    if root not in candidate.parents or candidate == root:
        raise UnsafeRecordingPath("录像文件不在受管目录")
    return candidate


def resolve_recording_path(
    recording_root: Path,
    relative_path: str,
    *,
    require_file: bool = True,
) -> Path:
    root = Path(recording_root).expanduser().resolve()
    candidate = _managed_file(root, root / relative_path)
    if require_file and not candidate.is_file():
        raise FileNotFoundError("录像文件不存在")
    return candidate


def has_recording_capacity(recording_root: Path, reserve_bytes: int) -> bool:
    root = Path(recording_root).expanduser().resolve()
    return shutil.disk_usage(root).free >= int(reserve_bytes)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def index_completed_recording(
    db,
    *,
    recording_root: Path,
    absolute_path: Path,
    live_session_id: int,
    now: datetime | None = None,
    duration_seconds: float = 0,
) -> models.LiveRecording:
    root = Path(recording_root).expanduser().resolve()
    candidate = _managed_file(root, Path(absolute_path))
    if not candidate.is_file():
        raise UnsafeRecordingPath("录像文件不在受管目录")
    relative_path = candidate.relative_to(root).as_posix()
    recording = (
        db.query(models.LiveRecording)
        .filter(models.LiveRecording.relative_path == relative_path)
        .one_or_none()
    )
    if recording is None:
        recording = models.LiveRecording(
            session_id=live_session_id,
            display_name=candidate.name,
            relative_path=relative_path,
        )
        db.add(recording)
    recording.file_size = candidate.stat().st_size
    recording.duration_seconds = max(0.0, float(duration_seconds))
    recording.sha256 = _sha256(candidate)
    recording.status = "ready"
    recording.ready_at = now or datetime.utcnow()
    db.commit()
    db.refresh(recording)
    return recording


def delete_recording(
    db,
    *,
    recording: models.LiveRecording,
    recording_root: Path,
) -> bool:
    root = Path(recording_root).expanduser().resolve()
    candidate = resolve_recording_path(
        root,
        recording.relative_path,
        require_file=False,
    )
    if not candidate.exists():
        recording.status = "missing"
        db.commit()
        db.refresh(recording)
        return False
    if not candidate.is_file():
        raise UnsafeRecordingPath("录像文件不在受管目录")
    candidate.unlink()
    db.delete(recording)
    db.commit()
    return True
