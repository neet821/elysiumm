import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import elysium_health_guard as guard


class HealthGuardTests(unittest.TestCase):
    def test_monitored_units_exclude_retired_articles_and_mineradio_services(self):
        self.assertEqual(
            guard.MONITORED_UNITS,
            (
                "nginx.service",
                "elysiumm-backend.service",
                "elysiumm-mediamtx.service",
            ),
        )

    def test_run_once_does_not_probe_or_restart_kavita(self):
        inspected_containers = []
        commands = []

        def healthy_container(name):
            inspected_containers.append(name)
            return True

        def successful_command(command, timeout):
            commands.append(list(command))
            return True

        with patch.object(guard, "docker_container_healthy", side_effect=healthy_container):
            with patch.object(guard, "command_succeeds", side_effect=successful_command):
                guard.run_once(guard.HealthGuard(action_runner=lambda command: True))

        self.assertEqual(inspected_containers, ["obsidian-livesync-couchdb"])
        self.assertFalse(any("kavita" in item.casefold() for item in inspected_containers))
        self.assertFalse(any("kavita" in part.casefold() for command in commands for part in command))

    def test_action_failure_is_logged_and_does_not_thrash(self):
        now = [1000.0]
        actions = []

        def fail_action(command):
            actions.append(command)
            return False

        health_guard = guard.HealthGuard(action_runner=fail_action, now=lambda: now[0])
        action = ["systemctl", "restart", "nginx"]
        for _ in range(3):
            health_guard.observe("nginx", False, action, threshold=3, cooldown=900)
        for _ in range(3):
            health_guard.observe("nginx", False, action, threshold=3, cooldown=900)
        self.assertEqual(actions, [action])


if __name__ == "__main__":
    unittest.main()
