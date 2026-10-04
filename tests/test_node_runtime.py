import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import subprocess

from deployment import node_runtime
from deployment.deploy_types import ProductionDeployError


class NodeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def archive(self, *, extra=None, license=True):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:xz") as archive:
            files = {
                "bin/node": b"verified-node",
                "lib/node_modules/npm/bin/npm-cli.js": b"npm",
            }
            if license:
                files["LICENSE"] = b"Node.js and bundled component licenses"
            for name, content in files.items():
                entry = tarfile.TarInfo(f"{node_runtime.NODE_ARCHIVE_ROOT}/{name}")
                entry.size = len(content)
                entry.mode = 0o755 if name == "bin/node" else 0o644
                archive.addfile(entry, io.BytesIO(content))
            npm = tarfile.TarInfo(f"{node_runtime.NODE_ARCHIVE_ROOT}/bin/npm")
            npm.type = tarfile.SYMTYPE
            npm.linkname = "../lib/node_modules/npm/bin/npm-cli.js"
            archive.addfile(npm)
            if extra:
                archive.addfile(extra)
        return data.getvalue()

    def install(self, data, *, version=None, checksum=None):
        with patch.object(node_runtime, "_download_archive", side_effect=lambda path: path.write_bytes(data)), \
                patch.object(node_runtime, "NODE_ARCHIVE_SHA256", checksum or hashlib.sha256(data).hexdigest()), \
                patch.object(node_runtime.platform, "system", return_value="Linux"), \
                patch.object(node_runtime.platform, "machine", return_value="x86_64"), \
                patch.object(node_runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout=version or f"v{node_runtime.NODE_VERSION}\n", stderr="")):
            return node_runtime.install_node_runtime(self.root)

    def test_installs_only_in_new_release_with_license_and_integrity_record(self):
        data = self.archive()
        runtime, metadata = self.install(data)
        self.assertEqual(runtime, self.root / ".node")
        self.assertEqual((runtime / "bin/node").read_bytes(), b"verified-node")
        self.assertEqual((runtime / "bin/npm").read_bytes(), b"npm")
        self.assertTrue((runtime / "LICENSE").is_file())
        self.assertEqual(metadata["version"], node_runtime.NODE_VERSION)
        self.assertEqual(metadata["archive_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(metadata["binary_sha256"], hashlib.sha256(b"verified-node").hexdigest())
        self.assertEqual(list(self.root.iterdir()), [runtime])

    def test_checksum_failure_never_publishes_runtime(self):
        with self.assertRaisesRegex(ProductionDeployError, "SHA-256"):
            self.install(self.archive(), checksum="0" * 64)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_path_traversal_and_external_symlink_are_rejected(self):
        for symlink in (False, True):
            entry = tarfile.TarInfo(f"{node_runtime.NODE_ARCHIVE_ROOT}/bin/../../../outside")
            if symlink:
                entry = tarfile.TarInfo(f"{node_runtime.NODE_ARCHIVE_ROOT}/bin/outside")
                entry.type = tarfile.SYMTYPE
                entry.linkname = "../../../outside"
            with self.subTest(symlink=symlink), self.assertRaisesRegex(ProductionDeployError, "unsafe"):
                self.install(self.archive(extra=entry))
            self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_license_and_wrong_version_do_not_publish(self):
        with self.assertRaisesRegex(ProductionDeployError, "incomplete"):
            self.install(self.archive(license=False))
        with self.assertRaisesRegex(ProductionDeployError, "version"):
            self.install(self.archive(), version="v18.20.4\n")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_symlink_cannot_be_an_archive_member_parent(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:xz") as archive:
            link = tarfile.TarInfo(f"{node_runtime.NODE_ARCHIVE_ROOT}/alias")
            link.type = tarfile.SYMTYPE
            link.linkname = "."
            archive.addfile(link)
            archive.addfile(tarfile.TarInfo(f"{node_runtime.NODE_ARCHIVE_ROOT}/alias/payload"))
        with self.assertRaisesRegex(ProductionDeployError, "unsafe"):
            self.install(data.getvalue())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_runtime_is_never_overwritten(self):
        runtime = self.root / ".node"
        runtime.mkdir()
        (runtime / "keep").write_text("verified old runtime")
        with self.assertRaisesRegex(ProductionDeployError, "already exists"):
            self.install(self.archive())
        self.assertEqual((runtime / "keep").read_text(), "verified old runtime")

    def test_unsupported_host_fails_before_download(self):
        with patch.object(node_runtime.platform, "system", return_value="Linux"), \
                patch.object(node_runtime.platform, "machine", return_value="aarch64"), \
                patch.object(node_runtime, "_download_archive") as download, \
                self.assertRaisesRegex(ProductionDeployError, "Linux x86_64"):
            node_runtime.install_node_runtime(self.root)
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
