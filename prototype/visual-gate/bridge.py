"""Real data for the visual gate.

The visual gate is a web page, and the mirror's data lives in the Pygame
app's modules. This is the join: it constructs those modules from the
same CONFIG the Pygame app uses, drives their update() loops on a timer,
and maps what they hold into the JSON shape the page renders.

Reusing the modules rather than re-fetching means one set of credentials,
one API tracker, one circuit breaker and one last-good cache, and the
fetch logic that is already proven on the Pi.

The one rule that matters here: a value that is not available is
omitted, never invented. snapshot() returns only the keys it actually
has, and the page draws only what it is given. A missing feed makes its
panel stay away; it never makes the mirror show a plausible number.

Import side effects: config.py calls pygame.font.init(), and a couple of
modules build fonts in their constructors, so SDL is pointed at the
dummy video driver first - this process never opens a window.
"""

import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, "..", ".."))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

logger = logging.getLogger("bridge")

# Open-Meteo WMO codes, collapsed to the four glyphs the page draws.
# Anything unrecognised becomes cloud, which is the honest default for a
# code we have not mapped: it says "weather" without claiming sun.
_WMO_GLYPH = {
    0: "sun", 1: "sun",
    2: "partly", 3: "cloud",
    45: "cloud", 48: "cloud",
}


def _glyph_for(code):
    if code is None:
        return "cloud"
    code = int(code)
    if code in _WMO_GLYPH:
        return _WMO_GLYPH[code]
    return "cloud"


def _num(value):
    """A finite float, or None. Modules use the string 'N/A' for absent."""
    if value is None or value == "N/A":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


class Bridge:
    """Owns the data modules and turns them into a page payload."""

    # Which module each part of the page needs. A module that fails to
    # construct simply is not here, and everything it fed stays absent.
    WANTED = ("weather", "stocks", "calendar", "fitbit", "news",
              "octopus_energy", "smarthome")

    def __init__(self):
        from config import CONFIG
        self.config = CONFIG
        self.modules = {}
        self._lock = threading.Lock()

        for name in self.WANTED:
            entry = CONFIG.get(name)
            if not isinstance(entry, dict) or "class" not in entry:
                logger.info("no config for %s; skipping", name)
                continue
            try:
                self.modules[name] = self._build(name, entry)
                logger.info("bridge: %s ready", name)
            except Exception as exc:
                # One dead feed must not take the mirror down with it.
                logger.warning("bridge: %s unavailable (%s)", name, exc)

        self.gate = CONFIG.get("visual_gate", {}) or {}

    @staticmethod
    def _build(name, entry):
        import importlib
        module_file = {
            "weather": "weather_module", "stocks": "stocks_module",
            "calendar": "calendar_module", "fitbit": "fitbit_module",
            "news": "news_module", "octopus_energy": "octopus_energy_module",
            "smarthome": "smarthome_module",
        }[name]
        cls = getattr(importlib.import_module(module_file), entry["class"])
        return cls(**(entry.get("params") or {}))

    def pump(self):
        """One non-blocking tick of every module.

        The modules submit network work to BackgroundFetcher and collect
        it on a later call, so this returns immediately and the data
        arrives over the following ticks.
        """
        for name, mod in self.modules.items():
            try:
                mod.update()
            except Exception as exc:
                logger.warning("bridge: %s update failed (%s)", name, exc)

    # ---- mapping ------------------------------------------------------
    #
    # Each of these returns None when its source has nothing real yet.

    def _weather(self):
        mod = self.modules.get("weather")
        data = getattr(mod, "weather_data", None) if mod else None
        if not data:
            return None

        temp = _num((data.get("main") or {}).get("temp"))
        if temp is None:
            return None

        block = (data.get("weather") or [{}])[0]
        out = {
            "temperature_c": int(round(temp)),
            "condition_label": (block.get("description") or "").capitalize(),
            "condition": (block.get("main") or "").lower(),
        }

        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        temps = hourly.get("temperature_2m") or []
        codes = hourly.get("weather_code") or []
        rain = hourly.get("precipitation_probability") or []

        # Start at the slot covering now, then every third hour.
        start = 0
        now_hour = datetime.now().strftime("%Y-%m-%dT%H:00")
        if now_hour in times:
            start = times.index(now_hour)

        row = []
        for i in range(start, min(start + 15, len(times)), 3):
            t = _num(temps[i]) if i < len(temps) else None
            if t is None:
                continue
            row.append({
                "at": times[i][11:16],
                "glyph": _glyph_for(codes[i] if i < len(codes) else None),
                "c": int(round(t)),
            })
        if row:
            out["hourly"] = row[:5]

        # A rain alert only when the forecast actually crosses the
        # threshold in the next few hours. No crossing, no alert, and
        # the weather panel does without it.
        threshold = int(self.gate.get("rain_probability_pct", 55))
        for i in range(start, min(start + 6, len(rain))):
            if _num(rain[i]) is not None and rain[i] >= threshold:
                minutes = (i - start) * 60
                if minutes <= 0:
                    out["alert_label"], out["alert_lead"] = "Raining", "now"
                elif minutes < 60:
                    out["alert_label"], out["alert_lead"] = "Rain in", f"{minutes} min"
                else:
                    hours = minutes // 60
                    out["alert_label"] = "Rain in"
                    out["alert_lead"] = f"{hours} hr" if hours == 1 else f"{hours} hrs"
                break
        return out

    def _biometrics(self):
        mod = self.modules.get("fitbit")
        data = getattr(mod, "data", None) if mod else None
        if not data:
            return None

        out = {}
        bpm = _num(data.get("resting_heart_rate"))
        if bpm is not None:
            out["resting_bpm"] = int(round(bpm))

        # Fitbit stores the current module value as HH:MM; older callers
        # may still provide minutes, so accept both real representations.
        raw_sleep = data.get("sleep")
        minutes = None
        if isinstance(raw_sleep, str) and ":" in raw_sleep:
            try:
                hours, mins = raw_sleep.split(":", 1)
                minutes = int(hours) * 60 + int(mins)
            except (TypeError, ValueError):
                minutes = None
        else:
            minutes = _num(raw_sleep)
        if minutes is not None and minutes > 0:
            out["sleep_total_minutes"] = int(minutes)
            out["sleep_label"] = f"{int(minutes) // 60}h {int(minutes) % 60:02d}m"

        steps = _num(data.get("steps"))
        if steps is not None:
            out["steps"] = int(steps)
        return out or None

    def _calendar(self):
        mod = self.modules.get("calendar")
        events = None
        if mod:
            parser = getattr(mod, "parsed_events", None)
            events = parser(4) if callable(parser) else getattr(mod, "events", None)
        if not events:
            return None

        now = datetime.now()
        out = []
        for ev in events[:4]:
            when = ev.get("when")
            if when is None:
                continue
            # The module hands back aware datetimes for timed events.
            local = when.astimezone() if when.tzinfo else when
            row = {
                "at": "all day" if ev.get("all_day") else local.strftime("%H:%M"),
                "title": ev.get("summary") or "",
                "tone": "cool",
            }
            if not out:
                ref = now.astimezone() if local.tzinfo else now
                row["minutes_until"] = max(0, int((local - ref).total_seconds() // 60))
            out.append(row)
        return out or None

    def _event(self):
        mod = self.modules.get("news")
        heads = getattr(mod, "headlines", None) if mod else None
        if not heads:
            return None
        top = heads[0]
        title = top.get("title")
        if not title:
            return None
        return {
            "kind": "news",
            "source": top.get("source") or "",
            "headline": title,
            "time": datetime.now().strftime("%H:%M"),
        }

    def _markets(self):
        mod = self.modules.get("stocks")
        data = getattr(mod, "stock_data", None) if mod else None
        if not data:
            return None

        out = []
        for sym, row in data.items():
            price = _num(row.get("price"))
            pct = _num(row.get("percent_change"))
            if price is None or pct is None:
                continue
            cell = {"sym": sym, "price": round(price, 2), "pct": round(pct, 2),
                    "currency": row.get("currency") or "£"}
            # The sparkline is drawn only when there is a real series to
            # draw. A flat invented line would read as a quiet stock.
            series = row.get("series")
            if series and len(series) >= 4:
                lo, hi = min(series), max(series)
                span = (hi - lo) or 1.0
                cell["spark"] = [round((v - lo) / span, 4) for v in series]
            out.append(cell)
        return out or None

    def _energy(self):
        """Home energy, assembled from whatever is actually reporting.

        Octopus supplies the tariff, today's consumption and the EV
        dispatch slots. Live power and solar generation are not in that
        API - they come from Home Assistant sensors, named in CONFIG
        under visual_gate. Without those names this returns the parts it
        has, and the panel draws only those.
        """
        out = {}

        octo = self.modules.get("octopus_energy")
        if octo is not None:
            kwh = _num(getattr(octo, "consumption_today_kwh", None))
            if kwh is not None:
                out["today_kwh"] = round(kwh, 2)
            pence = _num(getattr(octo, "cost_today_pence", None))
            if pence is not None:
                out["today_cost_p"] = int(round(pence))
            rate = _num(getattr(octo, "current_rate", None))
            if rate is not None:
                out["rate_p_kwh"] = round(rate, 2)
                out["offpeak"] = bool(getattr(octo, "is_offpeak", False))

            car = self._car(octo)
            if car:
                out["car"] = car

        live = self._ha_numbers()
        if live.get("watts_now") is not None:
            out["watts_now"] = int(round(live["watts_now"]))
            out["label"] = "Home usage"
        if live.get("solar_watts") is not None:
            out["solar_watts"] = int(round(live["solar_watts"]))
            out["solar_label"] = "Solar"
        if out.get("watts_now") is not None and out.get("solar_watts") is not None:
            out["grid_watts"] = out["watts_now"] - out["solar_watts"]
        if live.get("rooms_lit") is not None:
            out["rooms_lit"] = live["rooms_lit"]
        if live.get("rooms"):
            out["rooms"] = live["rooms"]

        return out or None

    def _car(self, octo):
        """Charging state from the Intelligent Octopus dispatch slots.

        A planned dispatch whose window covers now is the car actually
        drawing; that is what the panel means by charging.
        """
        planned = getattr(octo, "planned_dispatches", None) or []
        now = datetime.now(timezone.utc)
        charging = False
        for slot in planned:
            start = _parse_iso(slot.get("start") or slot.get("startDt"))
            end = _parse_iso(slot.get("end") or slot.get("endDt"))
            if start and end and start <= now <= end:
                charging = True
                break

        out = {"charging": charging}

        # State of charge, if the account exposes it. Octopus does not
        # always return one, and a charge level is not something to
        # guess at, so the panel goes without when it is missing.
        prefs = getattr(octo, "charge_prefs", None) or {}
        soc = _num(prefs.get("currentSoc") or prefs.get("soc"))
        if soc is None:
            soc = _num(self._ha_state(self.gate.get("car_soc_entity")))
        if soc is not None:
            out["charge_pct"] = int(round(soc))
        return out if (planned or "charge_pct" in out) else None

    # ---- Home Assistant -----------------------------------------------

    def _ha_states(self):
        mod = self.modules.get("smarthome")
        if mod is None:
            return {}
        all_states = getattr(mod, "_all_states", None)
        if isinstance(all_states, list):
            return {row.get("entity_id"): row for row in all_states
                    if isinstance(row, dict) and row.get("entity_id")}
        for attr in ("entity_states", "states", "entities", "data"):
            got = getattr(mod, attr, None)
            if isinstance(got, dict) and got:
                return got
        return {}

    def _ha_state(self, entity_id):
        if not entity_id:
            return None
        row = self._ha_states().get(entity_id)
        if isinstance(row, dict):
            return row.get("state")
        return row

    def _ha_numbers(self):
        out = {"watts_now": None, "solar_watts": None, "rooms_lit": None}
        out["watts_now"] = _num(self._ha_state(self.gate.get("power_entity")))
        out["solar_watts"] = _num(self._ha_state(self.gate.get("solar_entity")))

        lights = self.gate.get("light_entities") or []
        if lights:
            states = self._ha_states()
            if states:
                lit = 0
                for eid in lights:
                    row = states.get(eid)
                    state = row.get("state") if isinstance(row, dict) else row
                    if state == "on":
                        lit += 1
                out["rooms_lit"] = lit
        room_values = {}
        for room, prefix in (("upstairs", "upstairs"), ("downstairs", "downstairs")):
            temp = _num(self._ha_state(self.gate.get(f"{prefix}_temp_entity")))
            humidity = _num(self._ha_state(self.gate.get(f"{prefix}_humidity_entity")))
            if temp is not None:
                room_values.setdefault(room, {})["temperature_c"] = round(temp, 1)
            if humidity is not None:
                room_values.setdefault(room, {})["humidity_pct"] = round(humidity, 1)

        occupancy = self._ha_state(self.gate.get("bedroom_occupancy_entity"))
        if occupancy is not None and str(occupancy).lower() not in ("unknown", "unavailable"):
            room_values.setdefault("bedroom", {})["occupied"] = str(occupancy).lower() in ("on", "occupied", "home")

        curtain = self._ha_state(self.gate.get("livingroom_curtain_entity"))
        if curtain is not None and str(curtain).lower() not in ("unknown", "unavailable"):
            room_values.setdefault("livingroom", {})["curtain"] = str(curtain).lower()
        if room_values:
            out["rooms"] = room_values
        return out

    # ---- payload ------------------------------------------------------

    def snapshot(self):
        """The page payload. Only keys with real data behind them."""
        with self._lock:
            out = {"_live": True, "generated": int(time.time())}
            for key, fn in (("weather", self._weather),
                            ("biometrics", self._biometrics),
                            ("calendar", self._calendar),
                            ("event", self._event),
                            ("markets", self._markets),
                            ("energy", self._energy)):
                try:
                    value = fn()
                except Exception as exc:
                    logger.warning("bridge: %s mapping failed (%s)", key, exc)
                    value = None
                if value:
                    out[key] = value
            return out

    def control_status(self):
        """Safe diagnostics for the LAN control page; never expose secrets."""
        return {
            "modules": {name: True for name in sorted(self.modules)},
            "configured_entities": {
                key: bool(value) for key, value in self.gate.items()
                if key.endswith("_entity") or key == "light_entities"
            },
        }


def _parse_iso(text):
    if not text:
        return None
    try:
        cleaned = str(text).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def start(interval=1.0):
    """Build the bridge and keep pumping it on a daemon thread."""
    bridge = Bridge()

    def loop():
        while True:
            try:
                bridge.pump()
            except Exception:
                logger.exception("bridge pump failed")
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True, name="bridge").start()
    return bridge


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    b = start(interval=5.0)
    print("pumping; the first fetches take a few seconds\n")
    for _ in range(12):
        time.sleep(5)
        snap = b.snapshot()
        have = [k for k in snap if not k.startswith("_") and k != "generated"]
        print(f"  have: {', '.join(have) if have else '(nothing yet)'}")
    print()
    print(json.dumps(b.snapshot(), indent=2, default=str))
