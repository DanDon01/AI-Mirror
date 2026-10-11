"""Last-good data cache for AI-Mirror modules.

Network modules persist their most recent successful payload to disk so
that after a reboot the mirror shows real (if slightly stale) content
immediately instead of "Loading..." while the first fetches run.

Usage:
    from data_cache import data_cache
    data_cache.save("weather", {"data": ..., "source": ...})
    payload, age_sec = data_cache.load("weather", max_age_sec=86400)
"""

import json
import logging
import os
import time

logger = logging.getLogger("DataCache")

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.join(_PROJECT_DIR, "data", "cache")


class DataCache:
    def save(self, name, payload):
        """Persist a JSON-serialisable payload, written atomically."""
        try:
            os.makedirs(_CACHE_DIR, exist_ok=True)
            path = os.path.join(_CACHE_DIR, f"{name}.json")
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"saved_at": time.time(), "payload": payload}, f)
            os.replace(tmp, path)
        except Exception as e:
            logger.warning(f"Could not cache {name}: {e}")

    def load(self, name, max_age_sec=None):
        """Return (payload, age_seconds) or (None, None) if absent/expired."""
        try:
            path = os.path.join(_CACHE_DIR, f"{name}.json")
            if not os.path.exists(path):
                return None, None
            with open(path, "r", encoding="utf-8") as f:
                blob = json.load(f)
            age = time.time() - blob.get("saved_at", 0)
            if max_age_sec is not None and age > max_age_sec:
                return None, None
            return blob.get("payload"), age
        except Exception as e:
            logger.warning(f"Could not load cached {name}: {e}")
            return None, None


data_cache = DataCache()
