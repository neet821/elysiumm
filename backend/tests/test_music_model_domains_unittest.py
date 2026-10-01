"""Music model modules keep one metadata registry and legacy import paths."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models
from models import music, music_catalog, music_room, user_playlists


class MusicModelDomainsTest(unittest.TestCase):
    def test_each_model_group_has_a_domain_module(self):
        self.assertIs(music_catalog.CanonicalTrack, models.CanonicalTrack)
        self.assertIs(music_catalog.TrackProviderMapping, models.TrackProviderMapping)
        self.assertIs(music_catalog.TrackAudioSource, models.TrackAudioSource)
        self.assertIs(music_catalog.TrackLyrics, models.TrackLyrics)
        self.assertIs(music_room.MusicQueueItem, models.MusicQueueItem)
        self.assertIs(music_room.MusicRoomEvent, models.MusicRoomEvent)
        self.assertIs(music_room.MusicSkipVote, models.MusicSkipVote)
        self.assertIs(music_room.MusicTrackVote, models.MusicTrackVote)
        self.assertIs(music_room.MusicFavorite, models.MusicFavorite)
        self.assertIs(user_playlists.UserPlaylist, models.UserPlaylist)
        self.assertIs(user_playlists.UserPlaylistItem, models.UserPlaylistItem)

    def test_legacy_music_module_reexports_the_same_model_objects(self):
        for name in models.__all__:
            if name in {
                "CanonicalTrack",
                "TrackProviderMapping",
                "TrackAudioSource",
                "TrackLyrics",
                "MusicQueueItem",
                "MusicRoomEvent",
                "MusicSkipVote",
                "MusicTrackVote",
                "MusicFavorite",
                "UserPlaylist",
                "UserPlaylistItem",
            }:
                self.assertIs(getattr(music, name), getattr(models, name))

    def test_domain_modules_share_the_application_metadata(self):
        self.assertIs(music_catalog.Base, models.Base)
        self.assertIs(music_room.Base, models.Base)
        self.assertIs(user_playlists.Base, models.Base)
        self.assertIs(music.Base, models.Base)
        self.assertEqual(
            len([name for name in models.Base.metadata.tables if name.startswith(("canonical_", "track_", "music_", "user_playlist"))]),
            11,
        )

        models.Base.registry.configure()


if __name__ == "__main__":
    unittest.main()
