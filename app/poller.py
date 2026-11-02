from PySide6.QtCore import QThread, Signal
from .api import ApiError

class OrderPoller(QThread):
    orders_ready = Signal(list)
    poll_error = Signal(str)
    new_orders = Signal(list)

    def __init__(self, api, interval_seconds=30, parent=None):
        super().__init__(parent)
        self.api = api
        self.interval_seconds = max(30, int(interval_seconds))
        self._running = True
        self._previous_ids = set()
        self._first = True

    def set_interval(self, seconds):
        self.interval_seconds = max(30, int(seconds))

    def stop(self):
        self._running = False
        self.wait(20000)

    def run(self):
        while self._running:
            try:
                from datetime import date
                today = date.today().isoformat()
                result = self.api.orders("available", today, today)
                orders = result.get("data", [])
                ids = {int(x["id"]) for x in orders if x.get("id") is not None}
                if not self._first:
                    added = ids - self._previous_ids
                    if added:
                        self.new_orders.emit(sorted(added))
                self._first = False
                self._previous_ids = ids
                self.orders_ready.emit(orders)
            except ApiError as exc:
                self.poll_error.emit(str(exc))
            except Exception as exc:
                self.poll_error.emit(str(exc))
            # Interruptible in short slices so logout/close is responsive.
            for _ in range(self.interval_seconds * 10):
                if not self._running:
                    break
                self.msleep(100)
