"""In-memory progress state for the active /generate-tests run.

Single-user demo scope: one generation runs at a time, so one shared state
object is enough (same trade-off as the script registry). The generate router
updates it at each pipeline stage; GET /generate-progress reads it, and the
frontend polls that while the generate request is in flight.
"""
import threading


class ProgressTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = {"stage": "idle", "message": "", "current": None, "total": None}

    def set(self, stage: str, message: str, current: int | None = None, total: int | None = None) -> None:
        with self._lock:
            self._state = {"stage": stage, "message": message, "current": current, "total": total}

    def get(self) -> dict:
        with self._lock:
            return dict(self._state)


progress_tracker = ProgressTracker()
