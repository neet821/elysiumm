import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from catalog_domain import (  # noqa: E402
    ProviderTrack,
    TrackAvailability,
    canonical_group_payload,
    canonicalize_tracks,
    normalize_identity,
)


def provider_track(**overrides):
    values = {
        "album": "Blue Album",
        "artist": "Alice feat. Bob",
        "artwork_url": "https://img.example/blue.jpg",
        "availability": TrackAvailability.PLAYABLE,
        "duration_seconds": 180,
        "fee": 0,
        "isrc": None,
        "media_mid": None,
        "metadata": {},
        "provider": "netease",
        "provider_track_id": "track-1",
        "region": None,
        "title": "Blue Hour",
    }
    values.update(overrides)
    return ProviderTrack(**values)


class CatalogDomainTest(unittest.TestCase):
    def test_provider_track_requires_identity_and_normalizes_values(self):
        track = provider_track(
            artist="  Alice  ",
            availability="preview",
            duration_seconds=180.7,
            provider=" NETEASE ",
            provider_track_id=" 42 ",
            title="  Blue Hour  ",
        )

        self.assertEqual(track.provider, "netease")
        self.assertEqual(track.provider_track_id, "42")
        self.assertEqual(track.title, "Blue Hour")
        self.assertEqual(track.artist, "Alice")
        self.assertEqual(track.duration_seconds, 181)
        self.assertEqual(track.availability, TrackAvailability.PREVIEW)

        for field, value in [
            ("provider", ""),
            ("provider_track_id", ""),
            ("title", ""),
            ("artist", ""),
        ]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                provider_track(**{field: value})
        with self.assertRaises(ValueError):
            provider_track(availability="vip-bypass")
        with self.assertRaises(ValueError):
            provider_track(duration_seconds=-1)

    def test_identity_normalization_is_unicode_case_and_punctuation_stable(self):
        self.assertEqual(normalize_identity("  HéLLo，  World!  "), "hello world")
        self.assertEqual(normalize_identity("蓝色　时刻"), "蓝色 时刻")
        self.assertEqual(normalize_identity(None), "")

    def test_isrc_is_the_strongest_merge_identity(self):
        groups = canonicalize_tracks([
            provider_track(
                isrc=" US-ABC-24-00001 ",
                provider="netease",
                provider_track_id="ne-1",
                title="Blue Hour",
            ),
            provider_track(
                artist="Different display credit",
                duration_seconds=184,
                isrc="usabc2400001",
                provider="qq",
                provider_track_id="qq-1",
                title="Blue Hour (single)",
            ),
        ])

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].isrc, "USABC2400001")
        self.assertEqual([track.provider for track in groups[0].providers], ["netease", "qq"])

    def test_title_artist_and_three_second_duration_tolerance_merge(self):
        groups = canonicalize_tracks([
            provider_track(provider="qq", provider_track_id="qq-1", duration_seconds=183),
            provider_track(provider="netease", provider_track_id="ne-1", duration_seconds=180),
            provider_track(provider="audius", provider_track_id="au-1", duration_seconds=184),
        ])

        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups[0].providers), 2)
        self.assertEqual(len(groups[1].providers), 1)

    def test_featured_artist_order_does_not_create_a_duplicate(self):
        groups = canonicalize_tracks([
            provider_track(provider="netease", provider_track_id="ne-1", artist="Alice feat. Bob"),
            provider_track(provider="qq", provider_track_id="qq-1", artist="Bob & Alice"),
        ])

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].normalized_artist, "alice bob")

    def test_recording_version_markers_remain_distinct(self):
        markers = ["Live", "Remix", "Instrumental", "Cover", "Explicit", "Acoustic", "Edit", "Remaster"]
        tracks = [provider_track(
            provider="qq",
            provider_track_id=f"qq-{marker.lower()}",
            title=f"Blue Hour ({marker})",
        ) for marker in markers]
        tracks.append(provider_track(provider="netease", provider_track_id="ne-original"))

        groups = canonicalize_tracks(tracks)

        self.assertEqual(len(groups), len(markers) + 1)
        self.assertEqual(len({group.normalized_title for group in groups}), len(markers) + 1)

    def test_availability_uses_best_truthful_provider_state(self):
        group = canonicalize_tracks([
            provider_track(provider="qq", provider_track_id="qq-1", availability="unavailable"),
            provider_track(provider="audius", provider_track_id="au-1", availability="preview"),
            provider_track(provider="netease", provider_track_id="ne-1", availability="playable"),
        ])[0]

        self.assertEqual(group.availability, TrackAvailability.PLAYABLE)
        payload = canonical_group_payload(group)
        self.assertEqual(payload["availability"], "playable")
        self.assertEqual(
            [(item["provider"], item["availability"]) for item in payload["providers"]],
            [("netease", "playable"), ("qq", "unavailable"), ("audius", "preview")],
        )
        self.assertNotIn("metadata", payload["providers"][0])

    def test_canonicalization_is_deterministic_and_deduplicates_provider_identity(self):
        tracks = [
            provider_track(provider="qq", provider_track_id="qq-1", title="Second Song"),
            provider_track(provider="netease", provider_track_id="ne-1"),
            provider_track(provider="qq", provider_track_id="qq-2"),
            provider_track(provider="netease", provider_track_id="ne-1", artwork_url=None),
        ]

        forward = [canonical_group_payload(group) for group in canonicalize_tracks(tracks)]
        reverse = [canonical_group_payload(group) for group in canonicalize_tracks(reversed(tracks))]

        self.assertEqual(forward, reverse)
        blue_hour = next(item for item in forward if item["title"] == "Blue Hour")
        self.assertEqual(len(blue_hour["providers"]), 2)
        self.assertEqual(
            [(item["provider"], item["provider_track_id"]) for item in blue_hour["providers"]],
            [("netease", "ne-1"), ("qq", "qq-2")],
        )


if __name__ == "__main__":
    unittest.main()
