import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rate_limit import SlidingWindowRateLimiter  # noqa: E402


class SlidingWindowRateLimiterTest(unittest.TestCase):
    def test_limit_expires_and_clear_removes_state(self):
        now = [100.0]
        limiter = SlidingWindowRateLimiter(clock=lambda: now[0])

        self.assertEqual(limiter.check("login:alice", limit=2, window_seconds=10), 0)
        self.assertEqual(limiter.check("login:alice", limit=2, window_seconds=10), 0)
        self.assertGreater(
            limiter.check("login:alice", limit=2, window_seconds=10),
            0,
        )

        now[0] = 111.0
        self.assertEqual(limiter.check("login:alice", limit=2, window_seconds=10), 0)
        limiter.clear()
        self.assertEqual(limiter.check("login:alice", limit=1, window_seconds=10), 0)


if __name__ == "__main__":
    unittest.main()
