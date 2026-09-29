import inspect
import unittest

from deployment import (
    deploy_types,
    infrastructure_apply,
    infrastructure_validation,
    systemd_operations,
)
from deployment import production_deploy


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


if __name__ == "__main__":
    unittest.main()
