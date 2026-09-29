import ast
import importlib
import importlib.util
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "music-service-structure-test-secret")

import music_room_events  # noqa: E402
import music_room_queue_service  # noqa: E402
import music_service  # noqa: E402


class MusicServiceStructureTest(unittest.TestCase):
    def test_read_payloads_are_owned_by_the_music_room_read_service(self):
        module_name = "music_room_read_service"
        self.assertIsNotNone(importlib.util.find_spec(module_name))
        read_service = importlib.import_module(module_name)

        for name in ("queue_payload", "proposal_vote_required", "skip_vote_required", "favorite_payload"):
            with self.subTest(name=name):
                self.assertIs(getattr(music_room_queue_service, name), getattr(read_service, name))
                self.assertIs(getattr(music_service, name), getattr(read_service, name))
                self.assertEqual(getattr(read_service, name).__module__, module_name)

    def test_legacy_service_reexports_event_and_queue_operations(self):
        event_names = (
            "ROOM_EVENT_SUMMARY_KEYS",
            "_safe_event_summary",
            "_parse_event_summary",
            "record_room_event",
            "room_history",
        )
        queue_names = (
            "_stage_track_transition",
            "queue_payload",
            "proposal_vote_required",
            "skip_vote_required",
            "_approve_proposal",
            "_track_stream_url",
            "_canonical_track_id",
            "propose_track",
            "vote_proposal",
            "add_to_queue",
            "select_track",
            "advance_queue",
            "remove_queue_item",
            "favorite_payload",
        )
        engagement_names = ("like_queue_item", "vote_skip")

        for name in event_names:
            with self.subTest(name=name):
                self.assertIs(getattr(music_service, name), getattr(music_room_events, name))
        for name in queue_names:
            with self.subTest(name=name):
                self.assertIs(getattr(music_service, name), getattr(music_room_queue_service, name))

        engagement_service = importlib.import_module("music_room_engagement_service")
        for name in engagement_names:
            with self.subTest(name=name):
                self.assertIs(getattr(music_service, name), getattr(engagement_service, name))

    def test_domain_dependency_flows_from_queue_to_events(self):
        def imported_modules(module):
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            names = {
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
            }
            names.update(
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            )
            return names

        self.assertIn("music_room_events", imported_modules(music_room_queue_service))
        self.assertNotIn("music_room_queue_service", imported_modules(music_room_events))
        self.assertNotIn("music_service", imported_modules(music_room_events))
        self.assertNotIn("music_service", imported_modules(music_room_queue_service))
        engagement_service = importlib.import_module("music_room_engagement_service")
        self.assertIn("music_room_queue_service", imported_modules(engagement_service))
        self.assertNotIn("music_room_engagement_service", imported_modules(music_room_queue_service))

    def test_legacy_module_is_a_facade_without_business_function_definitions(self):
        tree = ast.parse(Path(music_service.__file__).read_text(encoding="utf-8"))
        business_definitions = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]

        self.assertEqual(business_definitions, [])


if __name__ == "__main__":
    unittest.main()
