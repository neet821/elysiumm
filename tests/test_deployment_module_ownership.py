import ast
import inspect
import unittest

from deployment import (
    deploy_types,
    git_component,
    infrastructure_apply,
    infrastructure_validation,
    deployment_lock,
    release_state,
    runtime_dependencies,
    systemd_operations,
)
from deployment import production_deploy
from deployment import production_rollback


class DeploymentModuleOwnershipTest(unittest.TestCase):
    def test_infrastructure_validation_is_owned_by_its_domain_module(self):
        for name in (
            "_allow_initial_backend_current_verify_failure",
            "_allow_initial_tusd_current_verify_failure",
            "_validate_infrastructure",
        ):
            self.assertEqual(
                inspect.getmodule(getattr(infrastructure_validation, name)).__name__,
                "deployment.infrastructure_validation",
            )

    def test_production_deploy_keeps_compatibility_exports(self):
        for name in (
            "_allow_initial_backend_current_verify_failure",
            "_allow_initial_tusd_current_verify_failure",
            "_validate_infrastructure",
        ):
            self.assertIs(
                getattr(production_deploy, name),
                getattr(infrastructure_validation, name),
            )

    def test_options_and_errors_have_one_shared_type_owner(self):
        for name in (
            "DeploymentOptions",
            "InfrastructureApplyError",
            "ProductionDeployError",
        ):
            self.assertIs(
                getattr(production_deploy, name),
                getattr(deploy_types, name),
            )

    def test_infrastructure_changes_are_owned_by_their_domain_module(self):
        for name in (
            "_apply_infrastructure",
            "_config_diff",
            "_restore_infrastructure",
            "_unlink_if_present",
        ):
            self.assertEqual(
                inspect.getmodule(getattr(infrastructure_apply, name)).__name__,
                "deployment.infrastructure_apply",
            )

    def test_deploy_module_preserves_infrastructure_compatibility_exports(self):
        for name in (
            "_apply_infrastructure",
            "_config_diff",
            "_restore_infrastructure",
            "_unlink_if_present",
        ):
            self.assertIs(
                getattr(production_deploy, name),
                getattr(infrastructure_apply, name),
            )

    def test_systemd_commands_have_one_shared_owner_and_compatibility_exports(self):
        for name in ("_systemctl", "_systemd_state"):
            self.assertEqual(
                inspect.getmodule(getattr(systemd_operations, name)).__name__,
                "deployment.systemd_operations",
            )
            self.assertIs(
                getattr(production_deploy, name),
                getattr(systemd_operations, name),
            )

    def test_runtime_dependency_checks_have_one_domain_owner(self):
        for name in (
            "_install_backend_dependencies",
            "_music_api_service_installed",
            "_backend_release_has_music_api",
            "_tusd_service_installed",
            "_backend_release_has_tusd",
            "_python_version",
        ):
            self.assertEqual(
                inspect.getmodule(getattr(runtime_dependencies, name)).__name__,
                "deployment.runtime_dependencies",
            )
            self.assertIs(
                getattr(production_deploy, name),
                getattr(runtime_dependencies, name),
            )

    def test_git_component_materialization_has_a_source_module_owner(self):
        for name in ("_safe_extract_archive", "materialize_git_component"):
            self.assertEqual(
                inspect.getmodule(getattr(git_component, name)).__name__,
                "deployment.git_component",
            )
            self.assertIs(
                getattr(production_deploy, name),
                getattr(git_component, name),
            )

    def test_release_state_and_shared_deploy_lock_have_domain_owners(self):
        for module, names, module_name in (
            (
                release_state,
                ("_current_record", "current_snapshot"),
                "deployment.release_state",
            ),
            (deployment_lock, ("_deployment_lock",), "deployment.deployment_lock"),
        ):
            for name in names:
                self.assertEqual(
                    inspect.getmodule(getattr(module, name)).__name__,
                    module_name,
                )
                self.assertIs(
                    getattr(production_deploy, name),
                    getattr(module, name),
                )

    def test_rollback_no_longer_imports_the_production_deploy_orchestrator(self):
        tree = ast.parse(inspect.getsource(production_rollback))
        imported_modules = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertNotIn("deployment.production_deploy", imported_modules)


if __name__ == "__main__":
    unittest.main()
