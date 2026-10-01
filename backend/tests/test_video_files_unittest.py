import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import video_files


class VideoFilesTest(unittest.TestCase):
    def test_subtitle_requires_a_timeline_for_both_formats(self):
        for name, raw in [("empty.vtt", b"WEBVTT\n\ntext"), ("empty.srt", b"text")]:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "时间轴"):
                video_files.normalize_subtitle(name, raw)

    def test_srt_converts_timestamps_without_changing_caption(self):
        raw = b"1\n00:00:01,000 --> 00:00:02,500\nhello\n"
        self.assertEqual(
            video_files.normalize_subtitle("example.srt", raw),
            b"WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.500\nhello\n",
        )

    def test_ranges_clamp_end_and_support_suffix(self):
        for value, expected in [
            ("bytes=2-8", (2, 8)),
            ("bytes=2-50", (2, 9)),
            ("bytes=-3", (7, 9)),
            ("bytes=0-", (0, 9)),
        ]:
            with self.subTest(value=value):
                self.assertEqual(video_files.parse_byte_range(value, 10), expected)
        for value in ["bytes=10-", "bytes=-0", "bytes=3-2", "bytes=1-2,4-5"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                video_files.parse_byte_range(value, 10)
