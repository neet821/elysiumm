import os
import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_tmpdir = tempfile.TemporaryDirectory()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_tmpdir.name) / 'native-track.sqlite'}")
os.environ.setdefault("SECRET_KEY", "native-track-test-secret")

import models  # noqa: E402
from database import Base  # noqa: E402
from routers.music import MineradioTrack, _ensure_canonical_track  # noqa: E402
import catalog_repository  # noqa: E402


class NativeMusicTrackTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_native_netease_track_without_canonical_id_is_persisted_and_reused(self):
        payload = MineradioTrack(
            provider="netease",
            provider_track_id="22494904",
            title="Blue",
            artist="yung kai",
            album="single",
            duration_seconds=180,
            artwork_url="https://img.example/blue.jpg",
        )
        first = _ensure_canonical_track(payload, self.db)
        second = _ensure_canonical_track(payload, self.db)
        self.assertGreater(first, 0)
        self.assertEqual(first, second)
        mapping = catalog_repository.provider_mapping(self.db, "netease", "22494904")
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.canonical_track_id, first)

    def test_native_payload_rejects_unknown_provider_and_empty_provider_id(self):
        with self.assertRaises(ValidationError):
            MineradioTrack(provider="spotify", provider_track_id="sp-1", title="Song")
        with self.assertRaises(ValidationError):
            MineradioTrack(provider="netease", provider_track_id="", title="Song")


if __name__ == "__main__":
    unittest.main()
