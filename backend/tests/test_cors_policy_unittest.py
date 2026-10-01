import ast
import re
import unittest
from pathlib import Path

from cors_policy import build_cors_policy


BACKEND_DIR = Path(__file__).resolve().parents[1]
MAIN_SOURCE = BACKEND_DIR / "main.py"


class CorsPolicyTest(unittest.TestCase):
    def test_keeps_local_and_configured_origins(self):
        policy = build_cors_policy(["https://elysium.example.test", "https://admin.example.test"])

        self.assertEqual(
            policy["allow_origins"],
            [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:5174",
                "http://127.0.0.1:5174",
                "http://localhost:8000",
                "https://elysium.example.test",
                "https://admin.example.test",
            ],
        )

    def test_keeps_the_existing_codespaces_origin_expression(self):
        policy = build_cors_policy([])
        expression = policy["allow_origin_regex"]

        self.assertTrue(re.fullmatch(expression, "https://workspace.github.dev"))
        self.assertTrue(re.fullmatch(expression, "https://workspace.githubpreview.dev"))
        self.assertTrue(re.fullmatch(expression, "https://workspace.app.github.dev"))
        self.assertIsNone(re.fullmatch(expression, "http://workspace.github.dev"))
        self.assertIsNone(re.fullmatch(expression, "https://nested.workspace.github.dev"))

    def test_main_passes_the_shared_policy_to_cors_middleware(self):
        tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_middleware"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "CORSMiddleware"
        ]
        self.assertEqual(len(calls), 1)
        self.assertTrue(
            any(
                isinstance(keyword, ast.keyword)
                and keyword.arg is None
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "cors_policy"
                for keyword in calls[0].keywords
            ),
            "main must use the shared CORS policy without duplicating origin rules",
        )


if __name__ == "__main__":
    unittest.main()
