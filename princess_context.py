"""Read-only, freshness-checked snapshots of live mirror module state."""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json


MAX_AGE = {
    "news": timedelta(minutes=30),
    "weather": timedelta(minutes=45),
    "calendar": timedelta(hours=2),
    "smarthome": timedelta(minutes=5),
}


def _timestamp(value):
    return value.isoformat() if isinstance(value, datetime) and value != datetime.min else None


def _age(value, now):
    if not isinstance(value, datetime) or value == datetime.min:
        return None
    try:
        return max(0, int((now - value).total_seconds()))
    except TypeError:
        return None


def _record(available, source, updated, now, payload, reason=None):
    age = _age(updated, now)
    fresh = available and age is not None and age <= MAX_AGE[source].total_seconds()
    data = {
        "available": bool(fresh),
        "source": source,
        "updated_at": _timestamp(updated),
        "age_seconds": age,
    }
    if fresh:
        data["data"] = payload
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        data["dependency_fingerprint"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    else:
        data["reason"] = reason or ("stale data" if available else "source unavailable")
    return data


class PrincessContext:
    """Copies current module state; it never fetches or mutates module data."""

    def __init__(self, sources=None):
        self.sources = sources or {}

    def set_sources(self, sources):
        self.sources = sources or {}

    def snapshot(self, now=None):
        now = now or datetime.now()
        return {
            "news": self._news(now),
            "weather": self._weather(now),
            "calendar": self._calendar(now),
            "smarthome": self._smarthome(now),
        }

    def _news(self, now):
        module = self.sources.get("news")
        headlines = list(getattr(module, "headlines", []) or []) if module else []
        payload = [
            {"title": str(item.get("title", ""))[:300], "source": str(item.get("source", ""))[:80]}
            for item in headlines[:3] if isinstance(item, dict) and item.get("title")
        ]
        return _record(bool(payload), "news", getattr(module, "last_fetch", None), now, {"headlines": payload})

    def _weather(self, now):
        module = self.sources.get("weather")
        weather = getattr(module, "weather_data", None) if module else None
        if not isinstance(weather, dict):
            return _record(False, "weather", None, now, {})
        main = weather.get("main", {}) or {}
        conditions = weather.get("weather", []) or [{}]
        condition = conditions[0] if isinstance(conditions[0], dict) else {}
        payload = {
            "location": str(weather.get("name", ""))[:100],
            "temperature_c": main.get("temp"),
            "feels_like_c": main.get("feels_like"),
            "condition": str(condition.get("description", ""))[:100],
            "wind_mps": (weather.get("wind", {}) or {}).get("speed"),
        }
        return _record(bool(payload["location"]), "weather", getattr(module, "last_update", None), now, payload)

    def _calendar(self, now):
        module = self.sources.get("calendar")
        events = list(getattr(module, "events", []) or []) if module else []
        payload = []
        for event in events[:3]:
            if not isinstance(event, dict):
                continue
            start = event.get("start", {}) or {}
            when = start.get("dateTime") or start.get("date")
            summary = event.get("summary")
            if summary and when:
                payload.append({"title": str(summary)[:200], "start": str(when)[:80]})
        return _record(bool(payload), "calendar", getattr(module, "last_update", None), now, {"events": payload})

    def _smarthome(self, now):
        module = self.sources.get("smarthome")
        if not module or not getattr(module, "_connected", False):
            return _record(False, "smarthome", getattr(module, "last_update", None), now, {})
        entities = list(getattr(module, "entities", []) or [])
        states = getattr(module, "data", {}) or {}
        payload = []
        for entity_id in entities[:12]:
            info = states.get(entity_id, {}) if isinstance(states, dict) else {}
            attributes = info.get("attributes", {}) or {}
            state = info.get("state")
            if state and state not in ("unavailable", "unknown"):
                payload.append({
                    "name": str(attributes.get("friendly_name", entity_id))[:100],
                    "state": str(state)[:80],
                    "unit": str(attributes.get("unit_of_measurement", ""))[:20],
                })
        return _record(bool(payload), "smarthome", getattr(module, "last_update", None), now, {"entities": payload})
