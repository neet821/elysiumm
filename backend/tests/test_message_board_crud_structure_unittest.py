import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

MESSAGE_OPERATIONS = (
    "create_message_board_entry",
    "get_message_board_entries",
    "like_message",
    "delete_message",
)


class MessageBoardCrudStructureTest(unittest.TestCase):
    def test_legacy_crud_reexports_message_board_service_functions(self):
        self.assertIsNotNone(
            importlib.util.find_spec("message_board_crud"),
            "message-board persistence operations should have a dedicated module",
        )
        messages = importlib.import_module("message_board_crud")
        legacy_facade = importlib.import_module("crud")

        for name in MESSAGE_OPERATIONS:
            with self.subTest(name=name):
                self.assertIs(getattr(legacy_facade, name), getattr(messages, name))

        facade_tree = ast.parse(
            Path(legacy_facade.__file__).read_text(encoding="utf-8")
        )
        facade_definitions = {
            node.name
            for node in facade_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(facade_definitions.isdisjoint(MESSAGE_OPERATIONS))

    def test_message_board_service_does_not_import_legacy_crud_facade(self):
        self.assertIsNotNone(importlib.util.find_spec("message_board_crud"))
        module = importlib.import_module("message_board_crud")
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
        self.assertNotIn("crud", imported_modules)


if __name__ == "__main__":
    unittest.main()
