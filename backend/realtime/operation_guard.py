"""Bounded process-local ordering guard for versioned realtime operations."""

import time
import uuid
from collections import OrderedDict
from collections.abc import Callable


class RealtimeOperationSequenceGuard:
    """Reject duplicate or delayed operations from an opted-in client instance.

    State is intentionally process-local, matching the existing single-worker
    Socket.IO deployment. Calls are synchronous and contain no await point, so
    event-loop handlers cannot interleave a check/update pair.
    """

    def __init__(
        self,
        *,
        max_entries: int = 20_000,
        ttl_seconds: float = 86_400,
        clock: Callable[[], float] = time.monotonic,
    ):
        if max_entries < 1 or ttl_seconds <= 0:
            raise ValueError("operation guard bounds must be positive")
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._sequences: OrderedDict[tuple[int, int, str], tuple[int, float]] = (
            OrderedDict()
        )

    def clear(self) -> None:
        self._sequences.clear()

    def check(self, user_id: int, room_id: int, payload: dict) -> str:
        """Return legacy, accepted, duplicate, out_of_order, or invalid."""
        instance_id = payload.get("client_instance_id")
        sequence = payload.get("operation_seq")
        if instance_id is None and sequence is None:
            return "legacy"
        if (
            type(user_id) is not int
            or type(room_id) is not int
            or not isinstance(instance_id, str)
            or len(instance_id) != 36
            or type(sequence) is not int
            or sequence < 1
            or sequence > 9_007_199_254_740_991
        ):
            return "invalid"
        try:
            parsed_id = uuid.UUID(instance_id)
        except (ValueError, AttributeError):
            return "invalid"
        if str(parsed_id) != instance_id.lower():
            return "invalid"

        now = self.clock()
        while self._sequences:
            _, (_, updated_at) = next(iter(self._sequences.items()))
            if now - updated_at <= self.ttl_seconds:
                break
            self._sequences.popitem(last=False)

        key = (user_id, room_id, str(parsed_id))
        previous = self._sequences.get(key)
        if previous is not None and sequence <= previous[0]:
            return "duplicate" if sequence == previous[0] else "out_of_order"

        self._sequences[key] = (sequence, now)
        self._sequences.move_to_end(key)
        while len(self._sequences) > self.max_entries:
            self._sequences.popitem(last=False)
        return "accepted"
