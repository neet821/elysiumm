from __future__ import annotations

from pathlib import Path
import stat
import sys
import tempfile
import unittest
import hashlib

from deployment.release_builder import (
    ReleaseBuildError,
    assemble_backend_release,
    assemble_frontend_release,
    atomic_component_link,
)


SHA = "b" * 64


class ReleaseBuilderTests(unittest.TestCase):
    def test_backend_release_includes_checksum_recorded_tusd_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "backend-source"
            source.mkdir()
            (source / "requirements.txt").write_text("", encoding="utf-8")
            license_path = source / "third_party_licenses/tusd/LICENSE.txt"
            license_path.parent.mkdir(parents=True)
            license_path.write_text("tusd license notice\n", encoding="utf-8")
            tusd = root / "tusd"
            tusd.write_bytes(b"pinned tusd test binary")

            assembly = assemble_backend_release(
                root=root,
                release_id="abcdef1-tusd",
                deployment_id="tusd-deploy",
                git_commit="abcdef1234567890",
                backend_source=source,
                python_version="3.12",
                requirements_lock_sha256=SHA,
                api_schema_sha256=SHA,
                compatible_frontend_api="*",
                target_alembic_heads=["head"],
                python_executable=Path(sys.executable),
                freeze=False,
                tusd_binary=tusd,
            )

            installed = assembly.path / "backend/bin/tusd"
            self.assertEqual(installed.read_bytes(), tusd.read_bytes())
            self.assertTrue(installed.stat().st_mode & 0o111)
            self.assertEqual(
                (assembly.path / "backend/bin/tusd.LICENSE.txt").read_text(encoding="utf-8"),
                "tusd license notice\n",
            )
            self.assertEqual(
                assembly.manifest["tusd_binary_sha256"],
                hashlib.sha256(tusd.read_bytes()).hexdigest(),
            )

    def test_frontend_release_is_independent_and_switches_only_frontend(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "dist-source"
            source.mkdir()
            (source / "index.html").write_text("ok", encoding="utf-8")
            lock = root / "package-lock.json"
            lock.write_text("{}", encoding="utf-8")
            assembly = assemble_frontend_release(
                root=root,
                release_id="abcdef1-r1",
                deployment_id="deploy-1",
                git_commit="abcdef1234567890",
                dist_source=source,
                node_version="22",
                package_lock_sha256=SHA,
                api_schema_sha256=SHA,
                compatible_backend_api="^1",
                build_budget={"passed": True},
                git_ref="refs/heads/codex/release-cicd-2026-09-12",
                activate=True,
            )
            self.assertTrue((assembly.path / "dist/index.html").is_file())
            self.assertEqual(
                assembly.manifest["git_ref"],
                "refs/heads/codex/release-cicd-2026-09-12",
            )
            self.assertEqual((root / "frontend-current").resolve(), assembly.path)
            self.assertFalse((root / "backend-current").exists())
            self.assertFalse((assembly.path / "dist/index.html").is_symlink())
            self.assertEqual(stat.S_IMODE(assembly.path.stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE((assembly.path / "dist/index.html").stat().st_mode), 0o444)

    def test_backend_release_has_its_own_virtualenv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "backend-source"
            source.mkdir()
            (source / "main.py").write_text("app = None\n", encoding="utf-8")
            assembly = assemble_backend_release(
                root=root,
                release_id="abcdef1-r1",
                deployment_id="deploy-1",
                git_commit="abcdef1234567890",
                backend_source=source,
                python_version="3.12",
                requirements_lock_sha256=SHA,
                api_schema_sha256=SHA,
                compatible_frontend_api="^1",
                target_alembic_heads=["head"],
                python_executable=Path(sys.executable),
                create_virtualenv=True,
            )
            self.assertTrue((assembly.path / ".venv/pyvenv.cfg").is_file())
            self.assertTrue((assembly.path / "RELEASE.json").is_file())
            self.assertEqual(stat.S_IMODE(assembly.path.stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE((assembly.path / "backend/main.py").stat().st_mode), 0o444)
            self.assertEqual(stat.S_IMODE((assembly.path / "RELEASE.json").stat().st_mode), 0o444)

    def test_current_link_is_atomic_and_validates_component(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "releases/frontend-releases/abcdef1-r1"
            release.mkdir(parents=True)
            link = atomic_component_link(root, "frontend", "abcdef1-r1")
            self.assertEqual(link.resolve(), release)

    def test_current_link_refuses_regular_file_or_external_release_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "releases/frontend-releases/abcdef1-r1"
            release.mkdir(parents=True)
            current = root / "frontend-current"
            current.write_text("must not be replaced", encoding="utf-8")
            with self.assertRaises(ReleaseBuildError):
                atomic_component_link(root, "frontend", release.name)

            current.unlink()
            outside = root / "outside"
            outside.mkdir()
            (outside / "index.html").write_text("outside", encoding="utf-8")
            release.rmdir()
            release.symlink_to(outside)
            with self.assertRaises(ReleaseBuildError):
                atomic_component_link(root, "frontend", "abcdef1-r1")


if __name__ == "__main__":
    unittest.main()
