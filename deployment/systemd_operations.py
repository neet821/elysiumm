"""Guarded systemd commands used by production deployment operations."""

import subprocess

from deployment.deploy_types import ProductionDeployError


def _systemctl(action: str, service: str) -> None:
    if "flclash" in service.casefold():
        raise ProductionDeployError(
            f"deployment must not control FlClash service: {service}"
        )
    if action == "disable --now":
        command = ["systemctl", "disable", "--now", service]
    else:
        command = ["systemctl", action, service]
    subprocess.run(command, check=True)


def _systemd_state(unit: str) -> dict[str, bool]:
    """Capture state before a unit file is replaced or removed."""

    if "flclash" in unit.casefold():
        raise ProductionDeployError(f"deployment must not inspect FlClash unit: {unit}")
    enabled = (
        subprocess.run(
            ["systemctl", "is-enabled", "--quiet", unit],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )
    active = (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )
    return {"enabled": enabled, "active": active}
