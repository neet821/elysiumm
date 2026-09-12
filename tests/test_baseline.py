from __future__ import annotations

import json
from pathlib import Path
import subprocess
import stat
import tempfile
import unittest

from deployment.baseline import BaselineError, BaselineInputs, create_baseline, rewrite_paths


class BaselineTests(unittest.TestCase):
    def _components(self, root: Path, backend: Path | None = None) -> dict[str, Path]:
        components: dict[str, Path] = {}
        for name in ("backend", "frontend", "mineradio", "articles"):
            source = backend if name == "backend" and backend is not None else root / f"source-{name}"
            source.mkdir(parents=True, exist_ok=True)
            (source / f"{name}.txt").write_text(name, encoding="utf-8")
            components[name] = source
        return components

    def _valid_inputs(
        self,
        root: Path,
        *,
        components: dict[str, Path] | None = None,
        config_files: dict[str, Path] | None = None,
        runtime_dependencies: dict[str, Path] | None = None,
        services: tuple[str, ...] = (),
        service_commands: tuple[str, ...] = ("backend/.venv/bin/python -m uvicorn main:app --workers 1",),
    ) -> BaselineInputs:
        backup = root / "database-source.sql"
        backup.write_text("database backup\n", encoding="utf-8")
        environment = root / "backend.env"
        environment.write_text("DATABASE_URL=sqlite:////tmp/production.sqlite\n", encoding="utf-8")
        return BaselineInputs(
            baseline_root=root / "baseline",
            baseline_id="current-production-test",
            components=components or self._components(root),
            runtime_dependencies=runtime_dependencies or {},
            config_files=config_files or {"env/backend.env": environment},
            forbidden_references=(),
            external_shared_paths=("/shared",),
            production_revisions=("old",),
            target_heads=("old",),
            database_backup={"status": "captured", "path": "database/db.sql"},
            database_backup_path=backup,
            service_commands=service_commands,
            services=services,
        )

    def test_rewrite_rejects_original_runtime_reference(self):
        with self.assertRaises(BaselineError):
            rewrite_paths("WorkingDirectory=/old/release", {}, ("/old/release",))

    def test_baseline_copies_runtime_and_configs_without_source_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "app.py").write_text("print('ok')\n", encoding="utf-8")
            virtualenv = root / "runtime-venv"
            (virtualenv / "bin").mkdir(parents=True)
            python = virtualenv / "bin/python"
            python.write_text("#!/usr/bin/env bash\nexec /usr/bin/python3 \"$@\"\n", encoding="utf-8")
            python.chmod(0o755)
            (virtualenv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
            config = root / "service.env"
            config.write_text("ROOT=/shared\n", encoding="utf-8")
            inputs = self._valid_inputs(
                root,
                components=self._components(root, source),
                runtime_dependencies={"backend/.venv": virtualenv},
                config_files={"env/backend.env": config},
            )
            inputs = BaselineInputs(
                **{**inputs.__dict__, "restore_order": ("verify", "configuration", "database", "services")}
            )
            baseline = create_baseline(inputs)

            self.assertTrue((baseline / "backend/app.py").is_file())
            self.assertEqual(
                (baseline / "backend/.venv/bin/python").read_text(encoding="utf-8"),
                "#!/usr/bin/env bash\nexec /usr/bin/python3 \"$@\"\n",
            )
            self.assertTrue((baseline / "BASELINE.json").is_file())
            self.assertTrue((baseline / "SHA256SUMS").is_file())
            self.assertTrue((baseline / "restore/restore.sh").is_file())
            self.assertTrue((baseline / "restore/verify.sh").is_file())
            manifest = json.loads((baseline / "BASELINE.json").read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["runtime_dependencies"]["backend/.venv"]["baseline_path"],
                "backend/.venv",
            )
            self.assertEqual(
                manifest["service_commands"],
                ["backend/.venv/bin/python -m uvicorn main:app --workers 1"],
            )
            self.assertEqual(manifest["restore_order"], ["verify", "configuration", "database", "services"])
            self.assertEqual(set(manifest["components"]), {"backend", "frontend", "mineradio", "articles"})
            self.assertFalse(any(path.is_symlink() for path in baseline.rglob("*")))
            self.assertEqual(stat.S_IMODE((baseline / "BASELINE.json").stat().st_mode), 0o444)
            subprocess.run(["bash", str(baseline / "restore/verify.sh")], check=True, capture_output=True, text=True)

    def test_baseline_rejects_external_release_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            old = root / "old-release"
            old.mkdir()
            (old / "secret").write_text("no", encoding="utf-8")
            (source / "old-link").symlink_to(old)
            inputs = self._valid_inputs(root, components=self._components(root, source))
            inputs = BaselineInputs(**{**inputs.__dict__, "forbidden_references": (str(old),)})
            with self.assertRaises(BaselineError):
                create_baseline(inputs)

    def test_baseline_requires_database_revision_to_match_target_heads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._valid_inputs(root)
            inputs = BaselineInputs(
                **{
                    **inputs.__dict__,
                    "production_revisions": ("old",),
                    "target_heads": ("new",),
                }
            )
            with self.assertRaisesRegex(BaselineError, "exactly match"):
                create_baseline(inputs)

    def test_baseline_rewrites_and_checks_runtime_path_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            old_release = root / "old-release"
            old_release.mkdir()
            runtime_config = source / "runtime.conf"
            runtime_config.write_text(f"ROOT={old_release}\n", encoding="utf-8")
            virtualenv = root / "runtime-venv"
            (virtualenv / "bin").mkdir(parents=True)
            python = virtualenv / "bin/python"
            python.write_text("#!/usr/bin/env bash\nexec /usr/bin/python3 \"$@\"\n", encoding="utf-8")
            python.chmod(0o755)
            (virtualenv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
            inputs = self._valid_inputs(
                root,
                components=self._components(root, source),
                runtime_dependencies={"backend/.venv": virtualenv},
            )
            inputs = type(inputs)(
                **{
                    **inputs.__dict__,
                    "forbidden_references": (str(old_release),),
                }
            )
            with self.assertRaises(BaselineError):
                create_baseline(inputs)

            replacement = root / "baseline/current-production-test/backend"
            inputs = type(inputs)(
                **{
                    **inputs.__dict__,
                    "path_replacements": {str(old_release): str(replacement)},
                }
            )
            baseline = create_baseline(inputs)
            self.assertEqual(
                (baseline / "backend/runtime.conf").read_text(encoding="utf-8"),
                f"ROOT={replacement}\n",
            )

    def test_baseline_rejects_symlinked_config_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            real_config = root / "real.env"
            real_config.write_text("TOKEN=protected\n", encoding="utf-8")
            config_link = root / "backend.env"
            config_link.symlink_to(real_config)
            with self.assertRaises(BaselineError):
                create_baseline(self._valid_inputs(
                    root,
                    components=self._components(root, source),
                    config_files={"env/backend.env": config_link},
                ))

    def test_baseline_refuses_flclash_service_control(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            with self.assertRaises(BaselineError):
                create_baseline(self._valid_inputs(
                    root,
                    components=self._components(root, source),
                    services=("FlClashCore.service",),
                ))

    def test_baseline_rejects_external_uvicorn_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            with self.assertRaises(BaselineError):
                create_baseline(self._valid_inputs(
                    root,
                    components=self._components(root, source),
                    service_commands=("/opt/other/.venv/bin/python -m uvicorn main:app",),
                ))

    def test_baseline_id_is_a_single_safe_directory_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._valid_inputs(root)
            inputs = type(inputs)(**{**inputs.__dict__, "baseline_id": "../escape"})
            with self.assertRaises(BaselineError):
                create_baseline(inputs)


if __name__ == "__main__":
    unittest.main()
