import sys
import unittest
from pathlib import Path


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

    def test_finds_kavita_process_from_docker_top_output(self):
        output = "PID                 COMMAND\n1247                Kavita\n"
        self.assertEqual(guard.find_kavita_pid(output), "1247")
        self.assertIsNone(guard.find_kavita_pid("PID COMMAND\n"))

    def test_restarts_only_after_three_failures_and_respects_cooldown(self):
        now = [1000.0]
        actions = []
        health_guard = guard.HealthGuard(
            action_runner=lambda command: actions.append(command) or True,
            now=lambda: now[0],
        )

        for _ in range(2):
            health_guard.observe(
                "kavita",
                healthy=False,
                action=["docker", "restart", "kavita"],
                threshold=3,
                cooldown=900,
            )
        self.assertEqual(actions, [])

        health_guard.observe(
            "kavita",
            healthy=False,
            action=["docker", "restart", "kavita"],
            threshold=3,
            cooldown=900,
        )
        self.assertEqual(actions, [["docker", "restart", "kavita"]])

        health_guard.observe(
            "kavita",
            healthy=False,
            action=["docker", "restart", "kavita"],
            threshold=3,
            cooldown=900,
        )
        self.assertEqual(actions, [["docker", "restart", "kavita"]])

    def test_healthy_observation_resets_failure_streak(self):
        actions = []
        health_guard = guard.HealthGuard(
            action_runner=lambda command: actions.append(command) or True,
            now=lambda: 1000.0,
        )
        action = ["docker", "restart", "kavita"]

        health_guard.observe("kavita", False, action, threshold=3, cooldown=900)
        health_guard.observe("kavita", False, action, threshold=3, cooldown=900)
        health_guard.observe("kavita", True, action, threshold=3, cooldown=900)
        health_guard.observe("kavita", False, action, threshold=3, cooldown=900)
        self.assertEqual(actions, [])

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
