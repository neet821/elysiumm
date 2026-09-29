"""Stable import facade for legacy music model imports."""

from .base import Base
from .music_catalog import (
    CanonicalTrack,
    TrackAudioSource,
    TrackLyrics,
    TrackProviderMapping,
)
from .music_room import (
    MusicFavorite,
    MusicQueueItem,
    MusicRoomEvent,
    MusicSkipVote,
    MusicTrackVote,
)
from .user_playlists import UserPlaylist, UserPlaylistItem

__all__ = [
    "Base",
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
]
