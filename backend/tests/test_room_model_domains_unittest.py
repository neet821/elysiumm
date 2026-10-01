"""Room, video, and membership models retain one metadata registry."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models
from models import room_members, rooms, sync_rooms, video


class RoomModelDomainsTest(unittest.TestCase):
    def test_legacy_rooms_star_import_keeps_previous_exports(self):
        legacy_exports = (
            "Base",
            "BigInteger",
            "Boolean",
            "CheckConstraint",
            "Column",
            "DateTime",
            "Float",
            "ForeignKey",
            "Index",
            "Integer",
            "String",
            "Text",
            "UniqueConstraint",
            "datetime",
            "relationship",
            "SyncRoom",
            "VideoPlaylistItem",
            "VideoSubtitle",
            "VideoSession",
            "SyncRoomMember",
            "SyncRoomMessage",
        )
        self.assertEqual(set(rooms.__all__), set(legacy_exports))
        for name in legacy_exports:
            self.assertTrue(hasattr(rooms, name), name)

    def test_models_are_exposed_from_their_owning_domain_modules(self):
        self.assertIs(sync_rooms.SyncRoom, models.SyncRoom)
        self.assertIs(video.VideoPlaylistItem, models.VideoPlaylistItem)
        self.assertIs(video.VideoSubtitle, models.VideoSubtitle)
        self.assertIs(video.VideoSession, models.VideoSession)
        self.assertIs(room_members.SyncRoomMember, models.SyncRoomMember)
        self.assertIs(room_members.SyncRoomMessage, models.SyncRoomMessage)

    def test_legacy_rooms_module_reexports_the_same_classes(self):
        for name in (
            "SyncRoom",
            "VideoPlaylistItem",
            "VideoSubtitle",
            "VideoSession",
            "SyncRoomMember",
            "SyncRoomMessage",
        ):
            self.assertIs(getattr(rooms, name), getattr(models, name))

    def test_domain_modules_share_the_application_metadata(self):
        for module in (sync_rooms, video, room_members, rooms):
            self.assertIs(module.Base, models.Base)
        self.assertEqual(
            sum(
                name in models.Base.metadata.tables
                for name in (
                    "sync_rooms",
                    "video_playlist_items",
                    "video_subtitles",
                    "video_sessions",
                    "sync_room_members",
                    "sync_room_messages",
                )
            ),
            6,
        )
        models.Base.registry.configure()


if __name__ == "__main__":
    unittest.main()
