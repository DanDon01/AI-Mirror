"""Background fetch helper for AI-Mirror display modules.

Network calls must never run on the main render loop (30 FPS target).
Modules submit a fetch function here; it runs in a daemon thread and the
result is collected on a later frame via take_result().

Usage in a module's update():
    if self._fetcher.idle and time_to_refresh:
        self._fetcher.submit(self._fetch_data_blocking)
    result = self._fetcher.take_result()
    if result is not None:
        ok, value = result
        if ok:
            self.data = value
"""

import logging
import threading

logger = logging.getLogger("BackgroundFetcher")


class BackgroundFetcher:
    """Runs one fetch function at a time in a daemon thread.

    submit() is a no-op while a fetch is in flight, so calling it every
    frame is safe. take_result() returns (ok, value_or_exception) exactly
    once per completed fetch, or None if nothing has finished.
    """

    def __init__(self, name):
        self.name = name
        self._lock = threading.Lock()
        self._thread = None
        self._result = None  # (ok, value) tuple, consumed by take_result

    @property
    def idle(self):
        """True when no fetch is running."""
        with self._lock:
            return self._thread is None or not self._thread.is_alive()

    def submit(self, fn):
        """Start fn in a background thread. Returns False if already busy."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._thread = threading.Thread(
                target=self._run, args=(fn,),
                name=f"fetch-{self.name}", daemon=True,
            )
            self._thread.start()
            return True

    def _run(self, fn):
        try:
            value = fn()
            with self._lock:
                self._result = (True, value)
        except Exception as e:
            logger.warning(f"[{self.name}] background fetch failed: {e}")
            with self._lock:
                self._result = (False, e)

    def take_result(self):
        """Return and clear the last completed result, or None."""
        with self._lock:
            result = self._result
            self._result = None
            return result
