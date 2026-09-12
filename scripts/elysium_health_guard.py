#!/usr/bin/env python3
"""Local recovery guard for the Elysium and Kavita services.

The guard deliberately uses consecutive failures and cooldowns. A single slow
health check must not cause a production restart, and a failed restart must not
turn into a restart loop.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import time
from collections.abc import Callable, Sequence


LOGGER = logging.getLogger("elysium-health-guard")
KAVITA_URL = "http://127.0.0.1:5000/api/health"
BACKEND_URL = "http://127.0.0.1:8000/api/health"
WEBSITE_URL = "http://127.0.0.1/api/health"

MONITORED_UNITS = (
    "nginx.service",
    "elysiumm-backend.service",
    "elysiumm-articles.service",
    "elysiumm-mineradio.service",
    "elysiumm-mediamtx.service",
)


def run_command(command: Sequence[str], timeout: float) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        LOGGER.warning("command failed: %s (%s)", " ".join(command), error)
        return None


def command_succeeds(command: Sequence[str], timeout: float) -> bool:
    result = run_command(command, timeout)
    return result is not None and result.returncode == 0


def command_output(command: Sequence[str], timeout: float) -> str | None:
    result = run_command(command, timeout)
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip()


def docker_container_healthy(name: str) -> bool:
    status = command_output(
        [
            "docker",
            "inspect",
            "--format",
            "{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
            name,
        ],
        timeout=15,
    )
    return status == "true healthy"


def kavita_healthy() -> bool:
    return docker_container_healthy("kavita") and command_succeeds(
        ["curl", "-fsS", "--max-time", "10", KAVITA_URL],
        timeout=15,
    )


def find_kavita_pid(output: str | None) -> str | None:
    if not output:
        return None
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0].isdigit() and fields[1] == "Kavita":
            return fields[0]
    return None


def lower_kavita_io_priority() -> None:
    process_list = command_output(
        ["docker", "top", "kavita", "-eo", "pid,comm"],
        timeout=10,
    )
    pid = find_kavita_pid(process_list)
    if pid is not None:
        command_succeeds(["ionice", "-c", "2", "-n", "7", "-p", pid], timeout=10)


def couchdb_healthy() -> bool:
    # CouchDB's Docker health check already performs an authenticated /_up
    # request without exposing its credentials to this host-level process.
    return docker_container_healthy("obsidian-livesync-couchdb")


def unit_active(unit: str) -> bool:
    return command_succeeds(["systemctl", "is-active", "--quiet", unit], timeout=10)


class HealthGuard:
    """Apply failure thresholds and cooldowns to recovery actions."""

    def __init__(
        self,
        action_runner: Callable[[Sequence[str]], bool],
        now: Callable[[], float] = time.monotonic,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self.action_runner = action_runner
        self.now = now
        self.logger = logger
        self.failure_streak: dict[str, int] = {}
        self.last_action: dict[str, float] = {}

    def observe(
        self,
        name: str,
        healthy: bool,
        action: Sequence[str],
        threshold: int,
        cooldown: float,
    ) -> bool:
        if healthy:
            previous = self.failure_streak.get(name, 0)
            self.failure_streak[name] = 0
            if previous:
                self.logger.info("recovered: %s", name)
            return False

        streak = self.failure_streak.get(name, 0) + 1
        self.failure_streak[name] = streak
        if streak < threshold:
            self.logger.warning("unhealthy: %s (%d/%d)", name, streak, threshold)
            return False

        current_time = self.now()
        last_action = self.last_action.get(name)
        if last_action is not None and current_time - last_action < cooldown:
            return False

        self.logger.error("recovery action: %s -> %s", name, " ".join(action))
        succeeded = self.action_runner(action)
        self.last_action[name] = current_time
        self.failure_streak[name] = 0
        if not succeeded:
            self.logger.error("recovery action failed: %s", name)
        return True


def run_once(health_guard: HealthGuard) -> None:
    kavita_ok = kavita_healthy()
    health_guard.observe(
        "kavita",
        kavita_ok,
        ["docker", "restart", "kavita"],
        threshold=5,
        cooldown=900,
    )
    if kavita_ok:
        lower_kavita_io_priority()
    health_guard.observe(
        "couchdb",
        couchdb_healthy(),
        ["docker", "restart", "obsidian-livesync-couchdb"],
        threshold=6,
        cooldown=1200,
    )

    for unit in MONITORED_UNITS:
        health_guard.observe(
            f"unit:{unit}",
            unit_active(unit),
            ["systemctl", "restart", unit],
            threshold=3,
            cooldown=900,
        )

    if unit_active("nginx.service"):
        backend_ok = command_succeeds(
            ["curl", "-fsS", "--max-time", "10", BACKEND_URL],
            timeout=15,
        )
        health_guard.observe(
            "website-backend-http",
            backend_ok,
            ["systemctl", "restart", "elysiumm-backend.service"],
            threshold=3,
            cooldown=900,
        )

        website_ok = command_succeeds(
            ["curl", "-fsS", "--max-time", "10", WEBSITE_URL],
            timeout=15,
        )
        health_guard.observe(
            "website-nginx-route",
            website_ok,
            ["systemctl", "restart", "nginx.service"],
            threshold=3,
            cooldown=900,
        )


def execute_action(command: Sequence[str]) -> bool:
    result = run_command(command, timeout=120)
    return result is not None and result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run one check cycle and exit")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="log recovery actions without executing them",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.dry_run:
        action_runner = lambda command: LOGGER.warning(
            "dry-run, action skipped: %s", " ".join(command)
        ) or True
    else:
        action_runner = execute_action

    health_guard = HealthGuard(action_runner=action_runner)
    while True:
        run_once(health_guard)
        if args.once:
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
