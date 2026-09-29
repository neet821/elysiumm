import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_test_database = tempfile.TemporaryDirectory()
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(_test_database.name) / 'playlist-domains.sqlite'}",
)

import user_playlist_import_service  # noqa: E402
import user_playlist_service  # noqa: E402
import user_playlist_validation  # noqa: E402


class UserPlaylistServiceStructureTest(unittest.TestCase):
    def test_legacy_service_reexports_import_and_validation_domains(self):
        for name in ("import_public_playlist",):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(user_playlist_service, name),
                    getattr(user_playlist_import_service, name),
                )
        for name in (
            "MAX_PLAYLIST_TRACKS",
            "_NETEASE_ID",
            "_PROVIDERS",
            "normalize_netease_playlist_reference",
            "_validated_track_snapshot",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(user_playlist_service, name),
                    getattr(user_playlist_validation, name),
                )

    def test_import_service_does_not_depend_on_legacy_service(self):
        tree = ast.parse(
            Path(user_playlist_import_service.__file__).read_text(encoding="utf-8")
        )
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        self.assertNotIn("user_playlist_service", imports)

    def test_core_playlist_operations_remain_owned_by_service(self):
        for name in (
            "get_playlist",
            "list_playlists",
            "create_playlist",
            "rename_playlist",
            "delete_playlist",
            "add_track",
            "remove_track",
            "reorder_tracks",
            "playlist_payload",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(user_playlist_service, name).__module__,
                    "user_playlist_service",
                )


if __name__ == "__main__":
    unittest.main()
