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
    f"sqlite:///{Path(_test_database.name) / 'bookmark-domains.sqlite'}",
)

import bookmark_service  # noqa: E402
import bookmark_backup_service  # noqa: E402
import bookmark_collection_service  # noqa: E402
import bookmark_export_service  # noqa: E402
import bookmark_folder_service  # noqa: E402
import bookmark_html_parser  # noqa: E402
import bookmark_import_validation  # noqa: E402
import bookmark_public_service  # noqa: E402
import bookmark_restore_service  # noqa: E402
import bookmark_search_service  # noqa: E402
import bookmark_tag_service  # noqa: E402
import bookmark_transfer_service  # noqa: E402

DOMAIN_MODULES = {
    "bookmark_collection_service": bookmark_collection_service,
    "bookmark_export_service": bookmark_export_service,
    "bookmark_folder_service": bookmark_folder_service,
    "bookmark_import_validation": bookmark_import_validation,
    "bookmark_public_service": bookmark_public_service,
    "bookmark_search_service": bookmark_search_service,
    "bookmark_tag_service": bookmark_tag_service,
    "bookmark_transfer_service": bookmark_transfer_service,
    "bookmark_backup_service": bookmark_backup_service,
    "bookmark_restore_service": bookmark_restore_service,
}


EXPECTED_DOMAIN_EXPORTS = {
    "bookmark_collection_service": (
        "create_bookmark",
        "get_bookmark",
        "update_bookmark",
        "delete_bookmark",
        "bulk_update_bookmarks",
        "record_bookmark_visit",
    ),
    "bookmark_search_service": ("search_bookmarks",),
    "bookmark_tag_service": (
        "get_or_create_tag",
        "replace_bookmark_tags",
        "tags_for_bookmark",
    ),
    "bookmark_public_service": (
        "public_bookmarks",
        "public_folders",
        "serialize_public_bookmark",
    ),
    "bookmark_folder_service": (
        "MAX_FOLDER_DEPTH",
        "create_folder",
        "get_folder",
        "update_folder",
        "delete_folder",
    ),
    "bookmark_transfer_service": (
        "BookmarkImportValidationError",
        "BookmarkImportExecutionError",
        "export_bookmarks_json",
        "export_bookmarks_html",
        "import_bookmarks_json",
        "import_bookmarks_html",
        "serialize_import_job",
    ),
    "bookmark_export_service": (
        "export_bookmarks_json",
        "export_bookmarks_html",
    ),
    "bookmark_import_validation": (
        "BookmarkImportValidationError",
        "MAX_IMPORT_BYTES",
        "MAX_IMPORT_FOLDERS",
        "MAX_IMPORT_BOOKMARKS",
    ),
    "bookmark_backup_service": (
        "BookmarkBackupValidationError",
        "list_bookmark_backups",
        "bookmark_backup_output_dir",
        "create_bookmark_backup",
        "serialize_bookmark_backup",
    ),
    "bookmark_restore_service": (
        "restore_bookmark_backup",
    ),
}


class BookmarkServiceDomainsStructureTest(unittest.TestCase):
    def test_legacy_service_reexports_domain_callables(self):
        for module_name, names in EXPECTED_DOMAIN_EXPORTS.items():
            module = DOMAIN_MODULES[module_name]
            for name in names:
                with self.subTest(module=module_name, name=name):
                    self.assertIs(
                        getattr(bookmark_service, name),
                        getattr(module, name),
                    )

    def test_collection_module_keeps_folder_service_aliases(self):
        for name in (
            "MAX_FOLDER_DEPTH",
            "create_folder",
            "get_folder",
            "update_folder",
            "delete_folder",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(bookmark_collection_service, name),
                    getattr(bookmark_folder_service, name),
                )

    def test_collection_module_keeps_tag_service_aliases(self):
        for name in (
            "get_or_create_tag",
            "replace_bookmark_tags",
            "tags_for_bookmark",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(bookmark_collection_service, name),
                    getattr(bookmark_tag_service, name),
                )

    def test_collection_module_keeps_public_service_aliases(self):
        for name in (
            "public_bookmarks",
            "public_folders",
            "serialize_public_bookmark",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(bookmark_collection_service, name),
                    getattr(bookmark_public_service, name),
                )

    def test_collection_module_keeps_search_service_alias(self):
        self.assertIs(
            bookmark_collection_service.search_bookmarks,
            bookmark_search_service.search_bookmarks,
        )

    def test_transfer_facade_reexports_export_domain_callables(self):
        for name in ("export_bookmarks_json", "export_bookmarks_html"):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(bookmark_transfer_service, name),
                    getattr(bookmark_export_service, name),
                )

    def test_transfer_facade_keeps_the_legacy_html_parser_alias(self):
        self.assertIs(
            bookmark_transfer_service._BookmarkHTMLParser,
            bookmark_html_parser.BookmarkHTMLParser,
        )

    def test_transfer_facade_reexports_import_validation_contracts(self):
        for name in (
            "BookmarkImportValidationError",
            "MAX_IMPORT_BYTES",
            "MAX_IMPORT_FOLDERS",
            "MAX_IMPORT_BOOKMARKS",
            "_ImportFolder",
            "_ImportBookmark",
            "_BookmarkImportPlan",
            "_payload_from_json_input",
            "_normalize_import_plan",
            "_source_key",
            "_parse_last_visited",
            "_payload_from_html_input",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(bookmark_transfer_service, name),
                    getattr(
                        bookmark_import_validation,
                        "payload_from_html_input" if name == "_payload_from_html_input" else name,
                    ),
                )

    def test_domains_do_not_import_the_legacy_facade(self):
        for module_name, module in DOMAIN_MODULES.items():
            with self.subTest(module=module_name):
                tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imports.append(node.module or "")
                self.assertNotIn("bookmark_service", imports)

    def test_tag_and_public_domains_do_not_depend_on_collection_module(self):
        for module in (bookmark_tag_service, bookmark_public_service):
            with self.subTest(module=module.__name__):
                tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imports.append(node.module or "")
                self.assertNotIn("bookmark_collection_service", imports)

    def test_bookmark_domain_import_graph_is_acyclic(self):
        module_names = (
            "bookmark_backup_service",
            "bookmark_export_service",
            "bookmark_import_execution_service",
            "bookmark_restore_service",
            "bookmark_transfer_service",
        )
        module_set = set(module_names)
        dependencies = {}
        for module_name in module_names:
            source = BACKEND_DIR / f"{module_name}.py"
            tree = ast.parse(source.read_text(encoding="utf-8"))
            imported_modules = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_modules.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_modules.add(node.module)
            dependencies[module_name] = imported_modules & module_set

        visiting = set()
        visited = set()

        def visit(module_name):
            if module_name in visiting:
                return False
            if module_name in visited:
                return True
            visiting.add(module_name)
            if not all(visit(item) for item in dependencies[module_name]):
                return False
            visiting.remove(module_name)
            visited.add(module_name)
            return True

        self.assertTrue(
            all(visit(module_name) for module_name in module_names),
            f"bookmark domain import graph contains a cycle: {dependencies}",
        )


if __name__ == "__main__":
    unittest.main()
