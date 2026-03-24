from __future__ import annotations

from threading import Lock


class SchedulerLock:
    def __init__(self) -> None:
        self._lock = Lock()

    def acquire(self) -> bool:
        return self._lock.acquire(blocking=False)

    def release(self) -> None:
        if self._lock.locked():
            self._lock.release()

    def state(self) -> str:
        return "locked" if self._lock.locked() else "idle"


scheduler_lock = SchedulerLock()

