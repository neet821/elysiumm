import inspect
import unittest

from deployment import deploy_types, infrastructure_validation
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


if __name__ == "__main__":
    unittest.main()
