"""The small, local-only catalog used for the Elysium room playback trial."""

from __future__ import annotations

import json
import os
from pathlib import Path

import models

TEST_TRACKS = (
    {"slug": "frente-bizarre-love-triangle", "provider_track_id": "2587970", "title": "Bizarre Love Triangle", "artist": "Frente!", "album": "Marvin the Album [Mammoth]", "track": 14, "year": "1994", "duration": 120},
    {"slug": "xu-ru-yun-lei-hai", "provider_track_id": "307594", "title": "泪海", "artist": "许茹芸", "album": "泪海", "track": 1, "year": "1996", "duration": 298},
    {"slug": "elliott-smith-between-the-bars", "provider_track_id": "17566198", "title": "Between The Bars", "artist": "Elliott Smith", "album": "Either/Or", "track": 4, "year": "1997", "duration": 141},
    {"slug": "paramore-aint-it-fun", "provider_track_id": "26197534", "title": "Ain't It Fun", "artist": "Paramore", "album": "Paramore", "track": 6, "year": "2013", "duration": 297},
    {"slug": "fiona-apple-carrion", "provider_track_id": "17823137", "title": "Carrion", "artist": "Fiona Apple", "album": "Tidal", "track": 10, "year": "2000", "duration": 344},
)


def asset_dir() -> Path:
    return Path(os.getenv("MUSIC_TEST_DIR", str(Path(__file__).resolve().parents[1] / "music-test"))).expanduser()


def _norm(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def ensure_catalog(db):
    """Create/update only the five fixed catalog rows; return canonical rows."""
    rows = []
    for item in TEST_TRACKS:
        canonical = db.query(models.CanonicalTrack).filter_by(
            normalized_title=_norm(item["title"]),
            normalized_artist=_norm(item["artist"]),
            duration_seconds=item["duration"],
        ).first()
        if canonical is None:
            canonical = models.CanonicalTrack(
                title=item["title"], normalized_title=_norm(item["title"]),
                primary_artist=item["artist"], normalized_artist=_norm(item["artist"]),
                album=item["album"], duration_seconds=item["duration"],
                artwork_url=f"/music-test/{item['slug']}.jpg", availability="playable",
            )
            db.add(canonical)
            db.flush()
        else:
            canonical.title = item["title"]
            canonical.primary_artist = item["artist"]
            canonical.album = item["album"]
            canonical.artwork_url = f"/music-test/{item['slug']}.jpg"
            canonical.availability = "playable"
        mapping = db.query(models.TrackProviderMapping).filter_by(
            provider="netease", provider_track_id=item["provider_track_id"],
        ).first()
        if mapping is None:
            mapping = models.TrackProviderMapping(
                canonical_track_id=canonical.id, provider="netease",
                provider_track_id=item["provider_track_id"], availability="playable",
                metadata_json=json.dumps({"splayer_id": int(item["provider_track_id"])}),
            )
            db.add(mapping)
            db.flush()
        mapping.canonical_track_id = canonical.id
        source = db.query(models.TrackAudioSource).filter_by(canonical_track_id=canonical.id, source_type="local").first()
        if source is None:
            source = models.TrackAudioSource(canonical_track_id=canonical.id, source_type="local", availability="playable")
            db.add(source)
        source.playback_url = f"/music-test/{item['slug']}.mp3"
        source.availability = "playable"
        lrc_path = asset_dir() / f"{item['slug']}.lrc"
        lrc_text = lrc_path.read_text(encoding="utf-8") if lrc_path.exists() else ""
        lyrics = db.query(models.TrackLyrics).filter_by(canonical_track_id=canonical.id, provider="local", language="original").first()
        if lyrics is None:
            lyrics = models.TrackLyrics(canonical_track_id=canonical.id, provider="local", language="original")
            db.add(lyrics)
        lyrics.timed_text = lrc_text
        trans_path = asset_dir() / f"{item['slug']}.translation.lrc"
        lyrics.translation_text = trans_path.read_text(encoding="utf-8") if trans_path.exists() else None
        rows.append(canonical)
    db.commit()
    return rows


def item_for(db, *, canonical_id=None, provider_track_id=None):
    candidates = ensure_catalog(db)
    for canonical, item in zip(candidates, TEST_TRACKS):
        if canonical_id is not None and canonical.id == int(canonical_id):
            return canonical, item
        if provider_track_id is not None and item["provider_track_id"] == str(provider_track_id):
            return canonical, item
    raise ValueError("这首歌不在固定测试曲库中")


def payload(canonical, item):
    return {
        "id": canonical.id, "title": item["title"], "artist": item["artist"], "album": item["album"],
        "duration_seconds": item["duration"], "artwork_url": f"/music-test/{item['slug']}.jpg",
        "availability": "playable", "providers": [{"provider": "netease", "provider_track_id": item["provider_track_id"], "availability": "playable"}],
    }
