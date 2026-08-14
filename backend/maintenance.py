"""Process-local maintenance barrier for destructive database operations."""

from contextlib import contextmanager
from threading import RLock


class MaintenanceAlreadyActive(RuntimeError):
    pass


class MaintenanceController:
    def __init__(self) -> None:
        self._lock = RLock()
        self._active = False
        self._reason: str | None = None

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def reason(self) -> str | None:
        with self._lock:
            return self._reason

    def begin(self, reason: str) -> None:
        with self._lock:
            if self._active:
                raise MaintenanceAlreadyActive("maintenance is already active")
            self._active = True
            self._reason = reason

    def end(self) -> None:
        with self._lock:
            self._active = False
            self._reason = None

    @contextmanager
    def hold(self, reason: str):
        self.begin(reason)
        try:
            yield self
        finally:
            self.end()


maintenance_controller = MaintenanceController()
