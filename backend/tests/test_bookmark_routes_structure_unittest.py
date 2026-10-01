import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.routing import APIRoute


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_test_database = tempfile.TemporaryDirectory()
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(_test_database.name) / 'bookmark-routes.sqlite'}",
)
os.environ.setdefault("SECRET_KEY", "local-only-secret")

import bookmark_backup_service  # noqa: E402
import routers.bookmarks as legacy_bookmarks  # noqa: E402
import routers.bookmark_folders as bookmark_folders  # noqa: E402
import routers.bookmark_items as bookmark_items  # noqa: E402
import routers.bookmark_search_engines as bookmark_search_engines  # noqa: E402
import routers.bookmark_route_helpers as bookmark_route_helpers  # noqa: E402
import routers.bookmarks_public as bookmarks_public  # noqa: E402
import routers.bookmarks_transfer as bookmarks_transfer  # noqa: E402


EXPECTED_ROUTE_CONTRACT = [
    ("/public/collection", ("GET",)),
    ("/bookmark-folders", ("GET",)),
    ("/bookmark-folders", ("POST",)),
    ("/bookmark-folders/{folder_id}", ("PUT",)),
    ("/bookmark-folders/{folder_id}", ("DELETE",)),
    ("/bookmarks", ("GET",)),
    ("/bookmarks", ("POST",)),
    ("/bookmarks/export/json", ("GET",)),
    ("/bookmarks/import/json", ("POST",)),
    ("/bookmarks/export/html", ("GET",)),
    ("/bookmarks/import/html", ("POST",)),
    ("/bookmarks/backups", ("GET",)),
    ("/bookmarks/backups", ("POST",)),
    ("/bookmarks/backups/{backup_id}/restore", ("POST",)),
    ("/bookmarks/bulk", ("POST",)),
    ("/bookmarks/{bookmark_id}/visit", ("POST",)),
    ("/search-engines", ("GET",)),
    ("/search-engines", ("POST",)),
    ("/search-engines/{engine_id}", ("PUT",)),
    ("/search-engines/{engine_id}", ("DELETE",)),
    ("/bookmarks/{bookmark_id}", ("PUT",)),
    ("/bookmarks/{bookmark_id}", ("DELETE",)),
]


def route_contract(router):
    return [
        (route.path, tuple(sorted(route.methods or ())))
        for route in router.routes
        if isinstance(route, APIRoute)
    ]


class BookmarkRouteStructureTest(unittest.TestCase):
    def test_aggregator_preserves_route_paths_methods_and_order(self):
        self.assertEqual(
            route_contract(legacy_bookmarks.router),
            EXPECTED_ROUTE_CONTRACT,
        )

    def test_each_route_group_owns_only_its_expected_endpoints(self):
        self.assertEqual(
            route_contract(bookmarks_public.router),
            [("/public/collection", ("GET",))],
        )
        self.assertEqual(
            route_contract(bookmark_folders.router),
            EXPECTED_ROUTE_CONTRACT[1:5],
        )
        self.assertEqual(
            route_contract(bookmark_items.list_create_router),
            EXPECTED_ROUTE_CONTRACT[5:7],
        )
        self.assertEqual(
            route_contract(bookmarks_transfer.router),
            EXPECTED_ROUTE_CONTRACT[7:14],
        )
        self.assertEqual(
            route_contract(bookmark_items.activity_router),
            EXPECTED_ROUTE_CONTRACT[14:16],
        )
        self.assertEqual(
            route_contract(bookmark_search_engines.router),
            EXPECTED_ROUTE_CONTRACT[16:20],
        )
        self.assertEqual(
            route_contract(bookmark_items.update_delete_router),
            EXPECTED_ROUTE_CONTRACT[20:22],
        )

    def test_legacy_module_reexports_handler_objects(self):
        groups = (
            (bookmarks_public, ("get_public_collection",)),
            (
                bookmark_folders,
                (
                    "list_bookmark_folders",
                    "create_bookmark_folder",
                    "update_bookmark_folder",
                    "delete_bookmark_folder",
                ),
            ),
            (
                bookmark_items,
                (
                    "list_bookmarks",
                    "create_bookmark",
                    "bulk_update_bookmarks",
                    "visit_bookmark",
                    "update_bookmark",
                    "delete_bookmark",
                ),
            ),
            (
                bookmarks_transfer,
                (
                    "export_bookmarks_json",
                    "import_bookmarks_json",
                    "export_bookmarks_html",
                    "import_bookmarks_html",
                    "list_bookmark_backups",
                    "create_bookmark_backup",
                    "restore_bookmark_backup",
                ),
            ),
            (
                bookmark_search_engines,
                (
                    "list_search_engines",
                    "create_search_engine",
                    "update_search_engine",
                    "delete_search_engine",
                ),
            ),
        )
        for module, names in groups:
            for name in names:
                with self.subTest(module=module.__name__, name=name):
                    self.assertIs(
                        getattr(legacy_bookmarks, name),
                        getattr(module, name),
                    )

    def test_legacy_helpers_keep_their_public_imports(self):
        self.assertIs(
            legacy_bookmarks.bookmark_backup_output_dir,
            bookmark_backup_service.bookmark_backup_output_dir,
        )
        self.assertIs(
            legacy_bookmarks.model_updates,
            bookmark_route_helpers.model_updates,
        )
        self.assertIs(
            legacy_bookmarks.serialize_bookmark,
            bookmark_route_helpers.serialize_bookmark,
        )

    def test_route_domains_do_not_import_the_legacy_aggregator(self):
        modules = (
            bookmarks_public,
            bookmark_folders,
            bookmark_items,
            bookmark_search_engines,
            bookmark_route_helpers,
            bookmarks_transfer,
        )
        for module in modules:
            with self.subTest(module=module.__name__):
                tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imports.append(node.module or "")
                self.assertNotIn("routers.bookmarks", imports)


if __name__ == "__main__":
    unittest.main()
