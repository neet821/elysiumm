import ast
import importlib
import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("SECRET_KEY", "video-service-domains-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import video_item_service  # noqa: E402
import video_service  # noqa: E402
import video_subtitle_service  # noqa: E402


DOMAIN_EXPORTS = {
    "video_service_common": (
        "ensure_video_session",
        "_touch_room",
        "_project_legacy_video_fields",
    ),
    "video_item_service": (
        "validate_external_url",
        "create_playlist_item",
        "_item_cleanup_paths",
        "get_video_item",
        "update_item_metadata",
        "_item_payload",
    ),
    "video_session_service": (
        "replace_current_video_item",
        "current_video_snapshot",
        "video_snapshot_payload",
        "initialize_current_item_if_empty",
        "select_item",
        "apply_playback_update",
        "advance_playlist",
        "delete_playlist_item",
        "set_current_item",
    ),
    "video_playlist_service": (
        "reorder_playlist",
        "_next_item",
        "session_payload",
    ),
    "video_subtitle_service": (
        "select_subtitle",
        "delete_subtitle",
        "create_subtitle_record",
        "_subtitle_payload",
    ),
}


class VideoServiceDomainsStructureTest(unittest.TestCase):
    def test_item_payload_reuses_the_subtitle_domain_serializer(self):
        self.assertIs(
            video_item_service._item_payload.__globals__.get("_subtitle_payload"),
            video_subtitle_service._subtitle_payload,
        )

    def test_legacy_service_reexports_domain_functions_by_identity(self):
        for module_name, names in DOMAIN_EXPORTS.items():
            module = importlib.import_module(module_name)
            for name in names:
                with self.subTest(module=module_name, name=name):
                    self.assertIs(
                        getattr(video_service, name),
                        getattr(module, name),
                    )

    def test_domain_modules_do_not_import_the_legacy_facade(self):
        for module_name in DOMAIN_EXPORTS:
            module = importlib.import_module(module_name)
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            imported_modules = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported_modules.append(node.module or "")
            self.assertNotIn("video_service", imported_modules, module_name)


if __name__ == "__main__":
    unittest.main()
