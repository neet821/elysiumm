import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_tmpdir = tempfile.TemporaryDirectory()
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(_tmpdir.name) / 'catalog-persistence.sqlite'}",
)

import catalog_repository  # noqa: E402
import models  # noqa: E402
from catalog_domain import (  # noqa: E402
    ProviderTrack,
    TrackAvailability,
    canonicalize_tracks,
)
from database import Base  # noqa: E402


def _group(*tracks: ProviderTrack):
    groups = canonicalize_tracks(tracks)
    if len(groups) != 1:
        raise AssertionError("fixture tracks must form one canonical group")
    return groups[0]


class CatalogPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(bind=self.engine)
        session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_models_match_the_catalog_schema_contract(self):
        inspector = inspect(self.engine)
        self.assertTrue(
            {
                "canonical_tracks",
                "track_provider_mappings",
                "track_audio_sources",
                "track_lyrics",
            }.issubset(inspector.get_table_names())
        )

        mapping_uniques = inspector.get_unique_constraints("track_provider_mappings")
        self.assertIn(
            ["provider", "provider_track_id"],
            [constraint["column_names"] for constraint in mapping_uniques],
        )
        source_indexes = inspector.get_indexes("track_audio_sources")
        lyric_indexes = inspector.get_indexes("track_lyrics")
        self.assertIn(
            ["expires_at"],
            [index["column_names"] for index in source_indexes],
        )
        self.assertIn(
            ["expires_at"],
            [index["column_names"] for index in lyric_indexes],
        )

    def test_upsert_is_idempotent_and_preserves_provider_mapping_identity(self):
        first_group = _group(
            ProviderTrack(
                provider="netease",
                provider_track_id="ne-42",
                title="Blue Hour",
                artist="Alice feat. Bob",
                album="First",
                duration_seconds=180,
                isrc="US-AAA-26-00042",
                artwork_url="https://img.example/first.jpg",
                availability=TrackAvailability.PREVIEW,
                metadata={"quality": "standard"},
            ),
            ProviderTrack(
                provider="qq",
                provider_track_id="qq-42",
                title="blue hour",
                artist="Bob & Alice",
                duration_seconds=182,
                isrc="USAAA2600042",
                availability=TrackAvailability.PLAYABLE,
            ),
        )
        first = catalog_repository.upsert_canonical_groups(self.db, [first_group])
        self.assertEqual(len(first), 1)
        canonical_id = first[0].id
        mapping_id = catalog_repository.provider_mapping(
            self.db, "netease", "ne-42"
        ).id

        second_group = _group(
            ProviderTrack(
                provider="netease",
                provider_track_id="ne-42",
                title="Blue Hour (display update)",
                artist="Alice & Bob",
                duration_seconds=180,
                isrc="USAAA2600042",
                artwork_url="https://img.example/updated.jpg",
                availability=TrackAvailability.PLAYABLE,
                metadata={"quality": "lossless"},
            ),
        )
        second = catalog_repository.upsert_canonical_groups(self.db, [second_group])

        self.assertEqual(second[0].id, canonical_id)
        refreshed_mapping = catalog_repository.provider_mapping(
            self.db, "netease", "ne-42"
        )
        self.assertEqual(refreshed_mapping.id, mapping_id)
        self.assertEqual(refreshed_mapping.canonical_track_id, canonical_id)
        self.assertEqual(json.loads(refreshed_mapping.metadata_json)["quality"], "lossless")
        self.assertEqual(self.db.query(models.CanonicalTrack).count(), 1)
        self.assertEqual(self.db.query(models.TrackProviderMapping).count(), 2)

        payload = catalog_repository.canonical_payload(self.db, canonical_id)
        self.assertEqual(payload["id"], canonical_id)
        self.assertEqual(payload["availability"], "playable")
        self.assertEqual(
            [(item["provider"], item["provider_track_id"]) for item in payload["providers"]],
            [("netease", "ne-42"), ("qq", "qq-42")],
        )

    def test_metadata_json_is_valid_and_bounded(self):
        group = _group(
            ProviderTrack(
                provider="audius",
                provider_track_id="au-big",
                title="Bounded",
                artist="Payload",
                duration_seconds=30,
                availability=TrackAvailability.PLAYABLE,
                metadata={"description": "x" * 100_000, "nested": {"ok": True}},
            )
        )
        catalog_repository.upsert_canonical_groups(self.db, [group])
        mapping = catalog_repository.provider_mapping(self.db, "audius", "au-big")

        self.assertLessEqual(len(mapping.metadata_json.encode("utf-8")), 16_384)
        self.assertIsInstance(json.loads(mapping.metadata_json), dict)

    def test_deleting_canonical_track_cleans_up_owned_catalog_rows(self):
        group = _group(
            ProviderTrack(
                provider="qq",
                provider_track_id="qq-delete",
                title="Temporary",
                artist="Catalog",
                duration_seconds=60,
                availability=TrackAvailability.PREVIEW,
            )
        )
        canonical = catalog_repository.upsert_canonical_groups(self.db, [group])[0]
        mapping = catalog_repository.provider_mapping(self.db, "qq", "qq-delete")
        now = datetime.utcnow()
        self.db.add(
            models.TrackAudioSource(
                canonical_track_id=canonical.id,
                provider_mapping_id=mapping.id,
                source_type="public_preview",
                playback_url="https://audio.example/preview.mp3",
                availability="preview",
                expires_at=now + timedelta(minutes=5),
            )
        )
        self.db.add(
            models.TrackLyrics(
                canonical_track_id=canonical.id,
                provider_mapping_id=mapping.id,
                provider="qq",
                language="original",
                timed_text="[00:01.00]Temporary",
                fetched_at=now,
                expires_at=now + timedelta(days=1),
            )
        )
        self.db.commit()

        self.db.delete(canonical)
        self.db.commit()

        self.assertEqual(self.db.query(models.CanonicalTrack).count(), 0)
        self.assertEqual(self.db.query(models.TrackProviderMapping).count(), 0)
        self.assertEqual(self.db.query(models.TrackAudioSource).count(), 0)
        self.assertEqual(self.db.query(models.TrackLyrics).count(), 0)


if __name__ == "__main__":
    unittest.main()
