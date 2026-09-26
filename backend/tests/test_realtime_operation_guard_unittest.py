import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from realtime.operation_guard import RealtimeOperationSequenceGuard  # noqa: E402


class RealtimeOperationSequenceGuardTest(unittest.TestCase):
    CLIENT_ID = "00000000-0000-4000-8000-000000000001"

    def setUp(self):
        self.now = 100.0
        self.guard = RealtimeOperationSequenceGuard(
            max_entries=2,
            ttl_seconds=10,
            clock=lambda: self.now,
        )

    def test_accepts_legacy_clients_without_extension(self):
        self.assertEqual(
            self.guard.check(1, 2, {},),
            "legacy",
        )

    def test_rejects_duplicate_and_out_of_order_operations(self):
        payload = {"client_instance_id": self.CLIENT_ID, "operation_seq": 7}

        self.assertEqual(self.guard.check(1, 2, payload), "accepted")
        self.assertEqual(self.guard.check(1, 2, payload), "duplicate")
        self.assertEqual(
            self.guard.check(1, 2, {**payload, "operation_seq": 6}),
            "out_of_order",
        )
        self.assertEqual(
            self.guard.check(1, 2, {**payload, "operation_seq": 8}),
            "accepted",
        )

    def test_scopes_sequences_by_user_room_and_client_and_expires_old_entries(self):
        payload = {"client_instance_id": self.CLIENT_ID, "operation_seq": 1}
        self.assertEqual(self.guard.check(1, 2, payload), "accepted")
        self.assertEqual(self.guard.check(2, 2, payload), "accepted")
        self.assertEqual(self.guard.check(1, 3, payload), "accepted")

        self.now += 11
        self.assertEqual(self.guard.check(1, 2, payload), "accepted")

    def test_rejects_partial_or_invalid_extension(self):
        self.assertEqual(
            self.guard.check(1, 2, {"client_instance_id": self.CLIENT_ID}),
            "invalid",
        )
        self.assertEqual(
            self.guard.check(
                1,
                2,
                {"client_instance_id": "not-a-uuid", "operation_seq": 1},
            ),
            "invalid",
        )
        self.assertEqual(
            self.guard.check(
                1,
                2,
                {"client_instance_id": "a" * 37, "operation_seq": 1},
            ),
            "invalid",
        )
        self.assertEqual(
            self.guard.check(
                1,
                2,
                {"client_instance_id": "00000000-0000-4000-8000-000000000001", "operation_seq": True},
            ),
            "invalid",
        )


if __name__ == "__main__":
    unittest.main()
