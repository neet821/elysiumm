"""Release task: clear legacy music data and leave the fixed five-song catalog."""
from __future__ import annotations

from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from database import SessionLocal  # noqa: E402
import models  # noqa: E402
import music_test_catalog  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        db.query(models.MusicSkipVote).delete(synchronize_session=False)
        db.query(models.MusicTrackVote).delete(synchronize_session=False)
        db.query(models.MusicQueueItem).delete(synchronize_session=False)
        db.query(models.MusicRoomEvent).delete(synchronize_session=False)
        db.query(models.MusicFavorite).delete(synchronize_session=False)
        db.query(models.TrackLyrics).delete(synchronize_session=False)
        db.query(models.TrackAudioSource).delete(synchronize_session=False)
        db.query(models.TrackProviderMapping).delete(synchronize_session=False)
        db.query(models.CanonicalTrack).delete(synchronize_session=False)
        for room in db.query(models.SyncRoom).filter_by(mode="music").all():
            room.current_queue_item_id = None
            room.video_source = None
            room.current_time = 0
            room.is_playing = False
            room.playback_rate = 1.0
            room.playback_started_at_server_ms = 0
            room.playback_version = int(room.playback_version or 0) + 1
            room.music_skip_vote_percent = int(room.music_skip_vote_percent or 30)
        db.commit()
        rows = music_test_catalog.ensure_catalog(db)
        print(f"fixed catalog rows: {len(rows)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
