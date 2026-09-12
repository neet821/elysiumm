from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from alembic.config import Config
from alembic.script import ScriptDirectory

from deployment.migration_state import MigrationStateError, analyze_revision_graph


def script_directory(versions: dict[str, str | tuple[str, ...] | None]):
    root = Path(tempfile.mkdtemp())
    version_dir = root / "versions"
    version_dir.mkdir()
    for revision, down_revision in versions.items():
        value = repr(down_revision)
        (version_dir / f"{revision}_migration.py").write_text(
            f"revision = {revision!r}\ndown_revision = {value}\nbranch_labels = None\ndepends_on = None\n",
            encoding="utf-8",
        )
    config = Config()
    config.set_main_option("script_location", str(root))
    return ScriptDirectory.from_config(config)


class MigrationStateTests(unittest.TestCase):
    def test_equal_revision_requires_no_backup_or_upgrade(self):
        directory = script_directory({"b001": None, "head": "b001"})
        plan = analyze_revision_graph(directory, ["head"])
        self.assertEqual(plan.status, "not_required")
        self.assertEqual(plan.pending_revisions, ())

    def test_pending_descendant_is_reported(self):
        directory = script_directory({"b001": None, "middle": "b001", "head": "middle"})
        plan = analyze_revision_graph(directory, ["middle"])
        self.assertEqual(plan.status, "upgrade_required")
        self.assertEqual(plan.pending_revisions, ("head",))

    def test_multiple_heads_and_already_applied_branch_are_handled(self):
        directory = script_directory({
            "b001": None,
            "left": "b001",
            "right": "b001",
            "merge": ("left", "right"),
        })
        plan = analyze_revision_graph(directory, ["left", "right"], ["merge"])
        self.assertEqual(plan.pending_revisions, ("merge",))

    def test_target_behind_or_divergent_aborts(self):
        directory = script_directory({"b001": None, "old": "b001", "new": "b001"})
        with self.assertRaises(MigrationStateError):
            analyze_revision_graph(directory, ["new"], ["old"])

    def test_unknown_current_revision_aborts(self):
        directory = script_directory({"b001": None, "head": "b001"})
        with self.assertRaises(MigrationStateError):
            analyze_revision_graph(directory, ["missing"])


if __name__ == "__main__":
    unittest.main()
