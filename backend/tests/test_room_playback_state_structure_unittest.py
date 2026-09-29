import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

PUBLIC_OPERATIONS = (
    "_persist_authoritative_snapshot",
    "server_now_ms",
    "get_room_core_snapshot",
    "room_core_snapshot_payload",
    "persist_room_core_snapshot",
    "get_authoritative_snapshot",
    "authoritative_snapshot_payload",
    "apply_authoritative_track_update",
    "apply_authoritative_playback_update",
    "apply_playback_update",
)


class RoomPlaybackStateStructureTest(unittest.TestCase):
    def test_crud_facade_reexports_playback_authority_operations(self):
        self.assertIsNotNone(
            importlib.util.find_spec("room_playback_state"),
            "room playback authority should have a dedicated module",
        )
        playback_state = importlib.import_module("room_playback_state")
        legacy_facade = importlib.import_module("sync_room_crud")

        for name in PUBLIC_OPERATIONS:
            with self.subTest(name=name):
                self.assertIs(
                    getattr(legacy_facade, name),
                    getattr(playback_state, name),
                )

        facade_tree = ast.parse(
            Path(legacy_facade.__file__).read_text(encoding="utf-8")
        )
        facade_definitions = {
            node.name
            for node in facade_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(facade_definitions.isdisjoint(PUBLIC_OPERATIONS))

    def test_playback_state_module_does_not_import_legacy_crud_facade(self):
        self.assertIsNotNone(importlib.util.find_spec("room_playback_state"))
        module = importlib.import_module("room_playback_state")
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertNotIn("sync_room_crud", imported_modules)


if __name__ == "__main__":
    unittest.main()
