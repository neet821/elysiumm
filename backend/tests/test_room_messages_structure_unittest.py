import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class RoomMessagesStructureTest(unittest.TestCase):
    def test_crud_facade_reexports_message_service_functions(self):
        self.assertIsNotNone(
            importlib.util.find_spec("room_messages"),
            "room message operations should have a dedicated module",
        )
        messages = importlib.import_module("room_messages")
        room_time = importlib.import_module("room_time")
        legacy_facade = importlib.import_module("sync_room_crud")

        for name in ("create_message", "get_room_messages"):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(legacy_facade, name),
                    getattr(messages, name),
                )

        self.assertIs(legacy_facade.to_beijing_time, room_time.to_beijing_time)

        facade_tree = ast.parse(
            Path(legacy_facade.__file__).read_text(encoding="utf-8")
        )
        facade_definitions = {
            node.name
            for node in facade_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(
            facade_definitions.isdisjoint(
                {"create_message", "get_room_messages", "to_beijing_time"}
            )
        )

    def test_message_module_does_not_import_legacy_crud_facade(self):
        self.assertIsNotNone(importlib.util.find_spec("room_messages"))
        module = importlib.import_module("room_messages")
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
