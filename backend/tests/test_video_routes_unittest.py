import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


os.environ.setdefault("SECRET_KEY", "phase8-video-routes-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import database  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import room_cleanup_task  # noqa: E402
import schemas  # noqa: E402
import security  # noqa: E402
import sync_room_crud  # noqa: E402
import video_service  # noqa: E402
from external_media import ExternalMediaError, ExternalVideoProbe  # noqa: E402
from database import Base  # noqa: E402
from routers import video as video_router  # noqa: E402


class VideoRoutesTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.video_root = root / "videos"
        self.subtitle_root = root / "subtitles"
        self.video_root.mkdir()
        self.subtitle_root.mkdir()
        self.original_video_root = video_router.VIDEO_UPLOAD_ROOT
        self.original_subtitle_root = video_router.VIDEO_SUBTITLE_ROOT
        self.original_video_limit = video_router.MAX_VIDEO_SIZE_USER
        self.original_subtitle_limit = video_router.MAX_SUBTITLE_SIZE
        self.original_cleanup_video_root = room_cleanup_task.VIDEO_UPLOAD_ROOT
        self.original_cleanup_subtitle_root = room_cleanup_task.VIDEO_SUBTITLE_ROOT
        self.original_socket_emit = video_router.sio.emit
        self.original_external_probe = getattr(video_router, "inspect_external_video", None)
        self.emitted = []
        self.probed_urls = []

        async def fake_emit(event, data=None, room=None, skip_sid=None):
            self.emitted.append(
                {
                    "event": event,
                    "data": data or {},
                    "room": room,
                    "skip_sid": skip_sid,
                }
            )

        video_router.sio.emit = fake_emit

        async def fake_probe(url):
            self.probed_urls.append(url)
            if url.endswith("/watch"):
                raise ExternalMediaError("该地址不是可直接播放的视频文件或 m3u8 清单")
            is_hls = url.endswith(".m3u8")
            return ExternalVideoProbe(
                resolved_url=url,
                content_type="application/vnd.apple.mpegurl" if is_hls else "video/mp4",
                playback_kind="hls" if is_hls else "file",
                file_size=None if is_hls else 1200,
            )

        video_router.inspect_external_video = fake_probe
        video_router.video_buffer_states.clear()
        video_router.video_local_ready_states.clear()
        video_router.VIDEO_UPLOAD_ROOT = self.video_root
        video_router.VIDEO_SUBTITLE_ROOT = self.subtitle_root
        video_router.MAX_VIDEO_SIZE_USER = 64
        video_router.MAX_SUBTITLE_SIZE = 256
        room_cleanup_task.VIDEO_UPLOAD_ROOT = self.video_root
        room_cleanup_task.VIDEO_SUBTITLE_ROOT = self.subtitle_root

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.host = self.create_user("host", "host@example.com")
        self.member = self.create_user("member", "member@example.com")
        self.attacker = self.create_user("attacker", "attacker@example.com")
        self.room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(
                room_name="Video room",
                mode="url",
                type="video",
                control_mode="host_only",
            ),
            self.host.id,
        )
        sync_room_crud.join_room(self.db, self.room.id, self.member.id)

        def override_db():
            session = self.Session()
            try:
                yield session
            finally:
                session.close()

        main.app.dependency_overrides[database.get_db] = override_db
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()
        video_router.VIDEO_UPLOAD_ROOT = self.original_video_root
        video_router.VIDEO_SUBTITLE_ROOT = self.original_subtitle_root
        video_router.MAX_VIDEO_SIZE_USER = self.original_video_limit
        video_router.MAX_SUBTITLE_SIZE = self.original_subtitle_limit
        room_cleanup_task.VIDEO_UPLOAD_ROOT = self.original_cleanup_video_root
        room_cleanup_task.VIDEO_SUBTITLE_ROOT = self.original_cleanup_subtitle_root
        video_router.sio.emit = self.original_socket_emit
        if self.original_external_probe is None:
            delattr(video_router, "inspect_external_video")
        else:
            video_router.inspect_external_video = self.original_external_probe
        video_router.video_buffer_states.clear()
        video_router.video_local_ready_states.clear()
        self.temporary_directory.cleanup()

    def create_user(self, username, email):
        user = models.User(
            username=username,
            email=email,
            hashed_password="unused",
            role="user",
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def headers(self, user):
        token = security.create_access_token(
            {"sub": user.username, "user_id": user.id, "role": user.role}
        )
        return {"Authorization": f"Bearer {token}"}

    def create_external(self, title, url=None):
        response = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/url",
            headers=self.headers(self.host),
            json={
                "title": title,
                "source_url": url or f"https://media.example/{title}.mp4",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["item"]

    def test_detail_and_snapshot_are_member_only_and_path_safe(self):
        item = video_service.create_playlist_item(
            self.db,
            self.room,
            created_by=self.host.id,
            source_type="upload",
            title="Private film",
            storage_path="/srv/private/secret.mp4",
        )
        session = video_service.ensure_video_session(self.db, self.room)
        session.current_item_id = item.id
        self.db.commit()
        path = f"/api/video/rooms/{self.room.id}"

        self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(
            self.client.get(path, headers=self.headers(self.attacker)).status_code,
            403,
        )
        response = self.client.get(path, headers=self.headers(self.member))

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["snapshot"]["media_kind"], "video")
        self.assertEqual(payload["snapshot"]["media_id"], item.id)
        self.assertIn("access=", payload["session"]["playlist"][0]["playback_url"])
        self.assertNotIn("storage_path", str(payload))
        self.assertNotIn("/srv/private", str(payload))
        snapshot = self.client.get(
            f"{path}/snapshot",
            headers=self.headers(self.member),
        )
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.json()["media_id"], item.id)

    def test_first_added_video_becomes_current_without_autoplay_or_version_bump(self):
        first = self.create_external("first")
        detail = self.client.get(
            f"/api/video/rooms/{self.room.id}",
            headers=self.headers(self.member),
        ).json()

        self.assertEqual(detail["session"]["current_item_id"], first["id"])
        self.assertEqual(detail["snapshot"]["media_id"], first["id"])
        self.assertEqual(detail["snapshot"]["state"], "paused")
        self.assertEqual(detail["snapshot"]["version"], 0)

    def test_local_video_registers_only_metadata_and_exposes_required_fingerprint(self):
        fingerprint = "ab" * 32
        forbidden = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/local",
            headers=self.headers(self.member),
            json={"title": "本地影片", "filename": "movie.mp4", "file_size": 4096, "fingerprint": fingerprint},
        )
        self.assertEqual(forbidden.status_code, 403)

        created = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/local",
            headers=self.headers(self.host),
            json={"title": "本地影片", "filename": "../movie.mp4", "file_size": 4096, "fingerprint": fingerprint},
        )
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()["item"]
        session = created.json()["session"]
        self.assertEqual(item["source_type"], "legacy_local")
        self.assertEqual(item["original_filename"], "movie.mp4")
        self.assertEqual(item["local_fingerprint"], fingerprint)
        self.assertIsNone(item["playback_url"])
        self.assertEqual(session["current_source"], "legacy_local")
        self.assertEqual(session["required_local_fingerprint"], fingerprint)
        self.assertNotIn("storage_path", str(created.json()))
        self.assertNotIn("../", str(created.json()))

        invalid = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/local",
            headers=self.headers(self.host),
            json={"title": "无效", "filename": "bad.mp4", "file_size": 1, "fingerprint": "not-a-hash"},
        )
        self.assertEqual(invalid.status_code, 422)

    def test_room_detail_repairs_an_existing_playlist_without_a_current_item(self):
        item = video_service.create_playlist_item(
            self.db,
            self.room,
            created_by=self.host.id,
            source_type="upload",
            title="Existing upload",
            storage_path=str(self.video_root / "existing.mp4"),
        )
        session = video_service.ensure_video_session(self.db, self.room)
        self.assertIsNone(session.current_item_id)

        detail = self.client.get(
            f"/api/video/rooms/{self.room.id}",
            headers=self.headers(self.member),
        )

        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["session"]["current_item_id"], item.id)
        self.assertEqual(detail.json()["snapshot"]["media_id"], item.id)

    def test_url_replacement_keeps_one_current_item_and_updates_metadata(self):
        forbidden = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/url",
            headers=self.headers(self.member),
            json={"title": "No", "source_url": "https://media.example/no.mp4"},
        )
        self.assertEqual(forbidden.status_code, 403)
        for invalid_url in (
            "javascript:alert(1)",
            "https://user:pass@media.example/film.mp4",
            "https://media.example/line\nfeed.mp4",
            "//media.example/film.mp4",
        ):
            with self.subTest(url=invalid_url):
                response = self.client.post(
                    f"/api/video/rooms/{self.room.id}/items/url",
                    headers=self.headers(self.host),
                    json={"title": "Bad", "source_url": invalid_url},
                )
                self.assertIn(response.status_code, (400, 422))

        first = self.create_external("first")
        second = self.create_external("second")
        self.assertNotEqual(first["id"], second["id"])
        detail = self.client.get(
            f"/api/video/rooms/{self.room.id}",
            headers=self.headers(self.member),
        ).json()
        self.assertEqual(detail["session"]["current_item_id"], second["id"])
        self.assertEqual(
            [item["id"] for item in detail["session"]["playlist"]],
            [second["id"]],
        )
        self.db.refresh(self.room)
        self.assertEqual(self.room.playback_version, 1)
        self.assertIsNone(self.db.get(models.VideoPlaylistItem, first["id"]))

        metadata = self.client.put(
            f"/api/video/rooms/{self.room.id}/items/{second['id']}/metadata",
            headers=self.headers(self.host),
            json={"duration_seconds": 120.25, "width": 1920, "height": 1080},
        )
        self.assertEqual(metadata.status_code, 200, metadata.text)
        self.assertEqual(metadata.json()["resolution"], {"width": 1920, "height": 1080})
        self.assertEqual(metadata.json()["duration_seconds"], 120.25)
        self.db.refresh(self.room)
        self.assertEqual(self.room.playback_version, 1)
        invalid_metadata = self.client.put(
            f"/api/video/rooms/{self.room.id}/items/{second['id']}/metadata",
            headers=self.headers(self.host),
            json={"duration_seconds": -1, "width": 99999, "height": 0},
        )
        self.assertEqual(invalid_metadata.status_code, 422)

    def test_external_items_are_probed_and_return_only_protected_playback_urls(self):
        file_item = self.create_external("public-file", "https://media.example/movie.mp4")
        hls_item = self.create_external("public-hls", "https://media.example/master.m3u8")

        self.assertEqual(self.probed_urls, [
            "https://media.example/movie.mp4",
            "https://media.example/master.m3u8",
        ])
        self.assertEqual(file_item["playback_kind"], "file")
        self.assertEqual(hls_item["playback_kind"], "hls")
        self.assertTrue(file_item["playback_url"].startswith(f"/api/video/items/{file_item['id']}/stream?access="))
        self.assertTrue(hls_item["playback_url"].startswith(f"/api/video/items/{hls_item['id']}/stream?access="))
        self.assertNotIn("media.example", file_item["playback_url"])

        rejected = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/url",
            headers=self.headers(self.host),
            json={"title": "网页", "source_url": "https://media.example/watch"},
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("视频文件", rejected.json()["detail"])

    def test_video_upload_is_streamed_bounded_and_member_authorized(self):
        invalid = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/upload",
            headers=self.headers(self.host),
            files={"file": ("malware.exe", b"MZ", "video/mp4")},
        )
        self.assertEqual(invalid.status_code, 415)
        mismatch = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/upload",
            headers=self.headers(self.host),
            files={"file": ("clip.mp4", b"not-video", "text/plain")},
        )
        self.assertEqual(mismatch.status_code, 415)
        oversized = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/upload",
            headers=self.headers(self.host),
            files={"file": ("large.mp4", b"x" * 65, "video/mp4")},
        )
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(list(self.video_root.iterdir()), [])

        uploaded = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/upload",
            headers=self.headers(self.host),
            data={"title": "Uploaded"},
            files={"file": ("clip.mp4", b"small-video-bytes", "video/mp4")},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        item = uploaded.json()["item"]
        self.assertEqual(item["original_filename"], "clip.mp4")
        self.assertEqual(uploaded.json()["session"]["current_item_id"], item["id"])
        self.assertNotIn("storage_path", str(uploaded.json()))
        stored_files = list(self.video_root.iterdir())
        self.assertEqual(len(stored_files), 1)
        self.assertEqual(stored_files[0].read_bytes(), b"small-video-bytes")

        stream_path = f"/api/video/items/{item['id']}/stream"
        self.assertEqual(self.client.get(stream_path).status_code, 401)
        self.assertEqual(
            self.client.get(stream_path, headers=self.headers(self.attacker)).status_code,
            403,
        )
        streamed = self.client.get(stream_path, headers=self.headers(self.member))
        self.assertEqual(streamed.status_code, 200, streamed.text)
        self.assertEqual(streamed.content, b"small-video-bytes")
        self.assertEqual(streamed.headers["accept-ranges"], "bytes")

        ranged = self.client.get(
            stream_path,
            headers={**self.headers(self.member), "Range": "bytes=2-6"},
        )
        self.assertEqual(ranged.status_code, 206, ranged.text)
        self.assertEqual(ranged.content, b"all-v")
        self.assertEqual(ranged.headers["content-range"], "bytes 2-6/17")
        self.assertEqual(ranged.headers["content-length"], "5")
        self.assertEqual(ranged.headers["accept-ranges"], "bytes")

        suffix = self.client.get(
            stream_path,
            headers={**self.headers(self.member), "Range": "bytes=-5"},
        )
        self.assertEqual(suffix.status_code, 206, suffix.text)
        self.assertEqual(suffix.content, b"bytes")

        invalid_range = self.client.get(
            stream_path,
            headers={**self.headers(self.member), "Range": "bytes=99-100"},
        )
        self.assertEqual(invalid_range.status_code, 416, invalid_range.text)
        self.assertEqual(invalid_range.headers["content-range"], "bytes */17")
        detail = self.client.get(
            f"/api/video/rooms/{self.room.id}",
            headers=self.headers(self.member),
        ).json()
        signed_url = detail["session"]["playlist"][0]["playback_url"]
        self.assertEqual(self.client.get(signed_url).content, b"small-video-bytes")

    def test_external_file_and_hls_are_streamed_through_member_only_routes(self):
        calls = []

        class FakeRemote:
            def __init__(self, url, headers):
                self.url = url
                self.status_code = 206 if headers.get("Range") else 200
                if url.endswith("master.m3u8"):
                    self.status_code = 200
                    self.headers = {"content-type": "application/vnd.apple.mpegurl"}
                    self.content = b"#EXTM3U\n#EXTINF:4,\nsegment.ts\n"
                elif url.endswith("segment.ts"):
                    self.headers = {"content-type": "video/mp2t", "content-length": "7"}
                    self.content = b"segment"
                else:
                    self.headers = {
                        "content-type": "video/mp4",
                        "content-range": "bytes 2-6/17",
                        "content-length": "5",
                        "accept-ranges": "bytes",
                    }
                    self.content = b"all-v" if headers.get("Range") else b"small-video-bytes"

            async def aiter_bytes(self):
                yield self.content

            async def aclose(self):
                return None

        async def fake_open(url, *, headers=None):
            calls.append((url, dict(headers or {})))
            return FakeRemote(url, headers or {})

        original = getattr(video_router, "open_external_stream", None)
        video_router.open_external_stream = fake_open
        try:
            file_item = self.create_external("remote-file", "https://media.example/movie.mp4")
            file_url = file_item["playback_url"]
            self.assertEqual(self.client.get(file_url).status_code, 200)
            ranged = self.client.get(file_url, headers={"Range": "bytes=2-6"})
            self.assertEqual(ranged.status_code, 206)
            self.assertEqual(ranged.content, b"all-v")
            self.assertEqual(ranged.headers["content-range"], "bytes 2-6/17")
            self.assertEqual(calls[-1], ("https://media.example/movie.mp4", {"Range": "bytes=2-6"}))

            hls_item = self.create_external("remote-hls", "https://media.example/master.m3u8")
            playlist = self.client.get(hls_item["playback_url"])
            self.assertEqual(playlist.status_code, 200, playlist.text)
            self.assertIn(f"/api/video/items/{hls_item['id']}/hls?resource=", playlist.text)
            segment_path = next(line for line in playlist.text.splitlines() if line.startswith("/api/video/"))
            segment = self.client.get(segment_path)
            self.assertEqual(segment.status_code, 200, segment.text)
            self.assertEqual(segment.content, b"segment")
        finally:
            if original is None:
                delattr(video_router, "open_external_stream")
            else:
                video_router.open_external_stream = original

    def test_srt_subtitle_is_normalized_selected_and_safely_streamed(self):
        item = self.create_external("subtitled")
        srt = b"1\n00:00:01,000 --> 00:00:02,500\nHello\n"
        uploaded = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/{item['id']}/subtitles",
            headers=self.headers(self.host),
            data={"label": "English", "language": "en"},
            files={"file": ("film.srt", srt, "application/x-subrip")},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        subtitle = uploaded.json()["subtitle"]
        self.assertEqual(subtitle["format"], "vtt")
        stored = list(self.subtitle_root.iterdir())
        self.assertEqual(len(stored), 1)
        self.assertEqual(
            stored[0].read_text(),
            "WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.500\nHello\n",
        )

        selected_video = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/{item['id']}/select",
            headers=self.headers(self.host),
            json={"expected_version": 0, "autoplay": False},
        )
        self.assertEqual(selected_video.status_code, 200, selected_video.text)

        select = self.client.put(
            f"/api/video/rooms/{self.room.id}/subtitles/{subtitle['id']}/select",
            headers=self.headers(self.host),
        )
        self.assertEqual(select.status_code, 200, select.text)
        self.assertEqual(select.json()["selected_subtitle_id"], subtitle["id"])
        self.db.refresh(self.room)
        self.assertEqual(self.room.playback_version, 1)

        detail = self.client.get(
            f"/api/video/rooms/{self.room.id}",
            headers=self.headers(self.member),
        ).json()
        safe_subtitle = detail["session"]["playlist"][0]["subtitles"][0]
        self.assertIn("access=", safe_subtitle["src"])
        stream = self.client.get(
            f"/api/video/subtitles/{subtitle['id']}/stream",
            headers=self.headers(self.member),
        )
        self.assertEqual(stream.status_code, 200)
        self.assertTrue(stream.text.startswith("WEBVTT"))
        self.assertTrue(self.client.get(safe_subtitle["src"]).text.startswith("WEBVTT"))

        invalid = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/{item['id']}/subtitles",
            headers=self.headers(self.host),
            data={"label": "Bad", "language": "en"},
            files={"file": ("bad.srt", b"\xff\xfe\x00", "application/x-subrip")},
        )
        self.assertEqual(invalid.status_code, 400)
        oversized = self.client.post(
            f"/api/video/rooms/{self.room.id}/items/{item['id']}/subtitles",
            headers=self.headers(self.host),
            data={"label": "Large", "language": "en"},
            files={"file": ("large.vtt", b"WEBVTT\n" + b"x" * 300, "text/vtt")},
        )
        self.assertEqual(oversized.status_code, 413)

    def test_replacing_current_video_removes_previous_items(self):
        first = self.create_external("one")
        second = self.create_external("two")
        third = self.create_external("three")
        session = video_service.ensure_video_session(self.db, self.room)
        self.db.refresh(session)
        self.assertEqual(third["id"], session.current_item_id)
        self.assertIsNone(self.db.get(models.VideoPlaylistItem, first["id"]))
        self.assertIsNone(self.db.get(models.VideoPlaylistItem, second["id"]))

    def test_legacy_video_endpoints_delegate_to_the_video_session(self):
        legacy_url = self.client.put(
            f"/api/sync-rooms/{self.room.id}",
            headers=self.headers(self.host),
            json={
                "mode": "url",
                "video_source": "https://media.example/legacy.mp4",
            },
        )
        self.assertEqual(legacy_url.status_code, 200, legacy_url.text)
        detail = self.client.get(
            f"/api/video/rooms/{self.room.id}",
            headers=self.headers(self.member),
        ).json()
        self.assertEqual(detail["snapshot"]["version"], 0)
        current = next(
            item
            for item in detail["session"]["playlist"]
            if item["id"] == detail["session"]["current_item_id"]
        )
        self.assertEqual(current["source_type"], "external")

        uploaded = self.client.post(
            f"/api/sync-rooms/{self.room.id}/upload-video",
            headers=self.headers(self.host),
            files={"file": ("legacy.mp4", b"legacy-video", "video/mp4")},
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertEqual(uploaded.json()["playback_version"], 0)
        self.assertIn("access=", uploaded.json()["video_url"])
        detail = self.client.get(
            f"/api/video/rooms/{self.room.id}",
            headers=self.headers(self.member),
        ).json()
        self.assertEqual(detail["snapshot"]["version"], 0)
        current = next(
            item
            for item in detail["session"]["playlist"]
            if item["id"] == detail["session"]["current_item_id"]
        )
        self.assertEqual(current["source_type"], "external")

        deleted = self.client.delete(
            f"/api/sync-rooms/{self.room.id}/video",
            headers=self.headers(self.host),
        )
        self.assertEqual(deleted.status_code, 400, deleted.text)
        detail = self.client.get(
            f"/api/video/rooms/{self.room.id}",
            headers=self.headers(self.member),
        ).json()
        self.assertEqual(detail["snapshot"]["version"], 0)
        self.assertEqual(detail["session"]["current_item_id"], current["id"])
        self.assertEqual([item["source_type"] for item in detail["session"]["playlist"]], ["external", "upload"])
        self.assertEqual(len(list(self.video_root.iterdir())), 1)

    def test_cleanup_and_streaming_never_follow_a_tampered_outside_path(self):
        outside = Path(self.temporary_directory.name) / "outside.mp4"
        outside.write_bytes(b"must-stay")
        item = video_service.create_playlist_item(
            self.db,
            self.room,
            created_by=self.host.id,
            source_type="upload",
            title="Tampered",
            storage_path=str(outside),
            owned_file=True,
        )
        self.room.lifecycle_status = "expired"
        self.db.commit()

        stream = self.client.get(
            f"/api/video/items/{item.id}/stream",
            headers=self.headers(self.host),
        )
        self.assertEqual(stream.status_code, 404)
        self.assertEqual(room_cleanup_task.cleanup_video_room_uploads(self.db), 0)
        self.assertTrue(outside.exists())

        managed = self.video_root / "managed.mp4"
        managed.write_bytes(b"owned")
        item.storage_path = str(managed)
        self.db.commit()
        self.assertEqual(room_cleanup_task.cleanup_video_room_uploads(self.db), 1)
        self.assertFalse(managed.exists())
        self.assertTrue(outside.exists())


if __name__ == "__main__":
    unittest.main()
