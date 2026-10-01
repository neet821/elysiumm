"""Metadata fingerprint prevents a package-only model refactor changing tables."""

import hashlib
import json
import sys
import unittest
from pathlib import Path

from sqlalchemy import PrimaryKeyConstraint

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models  # noqa: E402


_LEGACY_TABLES = frozenset(
    """admin_audit_logs admin_files admin_transfer_notes book_list_items book_lists
    bookmark_backups bookmark_export_jobs bookmark_folders bookmark_import_jobs
    bookmark_tag_relations bookmark_tags bookmarks books canonical_tracks
    homepage_settings link_categories live_allowed_users live_credentials
    live_invites live_messages live_recordings live_sessions live_settings
    live_viewer_sessions media_entries message_board message_likes music_favorites
    music_queue_items music_room_events music_skip_votes music_track_votes photo_tags
    photos post_tags posts realtime_event_audit_logs resource_requests search_engines
    sync_devices sync_events sync_files sync_room_members sync_room_messages
    sync_rooms sync_uploads tags track_audio_sources track_lyrics
    track_provider_mappings transfer_files transfer_sessions users
    video_playlist_items video_sessions video_subtitles website_links wishlist_replies""".split()
)


class ModelMetadataContractTest(unittest.TestCase):
    def test_existing_table_metadata_is_unchanged(self):
        metadata = models.Base.metadata
        self.assertTrue(_LEGACY_TABLES.issubset(metadata.tables))
        payload = []
        for table in sorted(
            (metadata.tables[name] for name in _LEGACY_TABLES),
            key=lambda item: item.name,
        ):
            columns = [
                {
                    "name": column.name,
                    "type": str(column.type),
                    "nullable": column.nullable,
                    "primary_key": column.primary_key,
                    "unique": column.unique,
                    "index": column.index,
                    "foreign_keys": sorted(
                        f"{foreign_key.target_fullname}:{foreign_key.ondelete}:{foreign_key.onupdate}"
                        for foreign_key in column.foreign_keys
                    ),
                    "default": bool(column.default),
                    "server_default": bool(column.server_default),
                }
                for column in table.columns
            ]
            constraints = []
            for constraint in table.constraints:
                if isinstance(constraint, PrimaryKeyConstraint):
                    continue
                constraints.append(
                    {
                        "kind": type(constraint).__name__,
                        "name": constraint.name,
                        "columns": sorted(column.name for column in constraint.columns),
                        "sql": str(getattr(constraint, "sqltext", "")),
                    }
                )
            indexes = sorted(
                (index.name, sorted(column.name for column in index.columns), index.unique)
                for index in table.indexes
            )
            payload.append(
                {
                    "table": table.name,
                    "columns": columns,
                    "constraints": sorted(
                        constraints,
                        key=lambda item: (
                            item["kind"],
                            item["name"] or "",
                            item["columns"],
                            item["sql"],
                        ),
                    ),
                    "indexes": indexes,
                }
            )

        signature = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(len(payload), len(_LEGACY_TABLES))
        self.assertEqual(
            signature,
            "e8ca705e9599120e4cca05c157794075e7a8d4602eef8558604888accf98fdd5",
        )


if __name__ == "__main__":
    unittest.main()
