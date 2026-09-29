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
import bookmark_html_parser  # noqa: E402
import bookmark_import_validation  # noqa: E402
import bookmark_transfer_service  # noqa: E402

DOMAIN_MODULES = {
    "bookmark_collection_service": bookmark_collection_service,
    "bookmark_export_service": bookmark_export_service,
    "bookmark_import_validation": bookmark_import_validation,
    "bookmark_transfer_service": bookmark_transfer_service,
    "bookmark_backup_service": bookmark_backup_service,
}


EXPECTED_DOMAIN_EXPORTS = {
    "bookmark_collection_service": (
        "create_folder",
        "get_folder",
        "update_folder",
        "delete_folder",
        "get_or_create_tag",
        "create_bookmark",
        "get_bookmark",
        "replace_bookmark_tags",
        "update_bookmark",
        "delete_bookmark",
        "bulk_update_bookmarks",
        "search_bookmarks",
        "record_bookmark_visit",
        "public_bookmarks",
        "public_folders",
        "serialize_public_bookmark",
        "tags_for_bookmark",
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


if __name__ == "__main__":
    unittest.main()
