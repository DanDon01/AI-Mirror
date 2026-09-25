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
import json
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, "..", ".."))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

logger = logging.getLogger("bridge")
SETTINGS_PATH = os.path.join(HERE, "settings.json")
TWIN_ENTITIES = {
    'livingroom_light_entity', 'bedroom_light_entity', 'upstairs_light_entity',
    'porch_light_entity', 'hall_light_entity',
    'bedroom1_light_entity', 'bedroom2_light_entity', 'bedroom3_light_entity',
    'bathroom_light_entity', 'livingroom_spotlights_entity',
    'livingroom_led_entity', 'livingroom_tv_entity', 'alarm_entity',
    'car_presence_entity', 'upstairs_occupancy_entity', 'front_door_contact_entity',
    'doorbell_camera_entity', 'external_camera_entity',
    'doorbell_motion_entity', 'external_motion_entity', 'car_charging_entity',
    'battery_soc_entity', 'battery_charging_entity', 'entrance_pir_entity',
}


class EventHub:
    """Fan-out of small push events (presence, resident, moments) to every
    open page. Each subscriber gets its own bounded queue; a page that stops
    reading loses old events rather than growing memory without limit."""

    def __init__(self):
        import queue
        self._queue = queue
        self._subs = []
        self._lock = threading.Lock()

    def subscribe(self):
        q = self._queue.Queue(maxsize=64)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, event):
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(event)
            except self._queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass

# Open-Meteo WMO codes, collapsed to the four glyphs the page draws.
# Anything unrecognised becomes cloud, which is the honest default for a
# code we have not mapped: it says "weather" without claiming sun.
_WMO_GLYPH = {
    0: "sun", 1: "sun",
    2: "partly", 3: "cloud",
    45: "cloud", 48: "cloud",
}
for _code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
    _WMO_GLYPH[_code] = "rain"
for _code in (71, 73, 75, 77, 85, 86):
    _WMO_GLYPH[_code] = "cloud"
for _code in (95, 96, 99):
    _WMO_GLYPH[_code] = "storm"


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
    TUNING_DEFAULTS = {
        "home_orbit_seconds": 54, "home_orbit_angle": 45,
        "home_orbit_pause": 7, "home_camera_radius": 6.0,
        "home_camera_height": 4.25, "home_camera_fov": 33,
        "home_target_x": 1.25, "home_target_y": 1.08, "home_target_z": .95,
        "home_brightness": 1.0,
        "home_stage_scale": 1.0, "home_x": 0, "home_y": 0,
        "heart_x": 0, "heart_y": 0, "heart_scale": 1.0,
        "brain_x": 0, "brain_y": 0, "brain_scale": 1.0,
        "calendar_x": 0, "calendar_y": 0, "news_x": 0, "news_y": 0,
        # 0 = classic house (default until signed off), 1 = hologram.
        "home_renderer": 0,
        # Registers: minutes without presence before rest, and deep dim.
        "rest_after_minutes": 10, "dim_start_hour": 2, "dim_end_hour": 5,
        "dim_level": 0.35,
        # Resident: may speak unprompted (pooled clips only) after this
        # many minutes with nobody at the mirror. 0 turns it off.
        "resident_unprompted": 1, "resident_idle_minutes": 20,
        # Moments: ambient on/off, pacing, and real-data trigger thresholds.
        "moments_ambient": 1, "ambient_gap_minutes": 12, "ambient_daily_cap": 10,
        "steps_goal": 10000, "market_surge_pct": 7, "space_rocket_pct": 5,
    }

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

        self.gate = dict(CONFIG.get("visual_gate", {}) or {})
        self.events = EventHub()
        # Moments are played by the page; the bridge keeps the owner's
        # on/off choices and a short log of what played and why.
        self.moments = {"catalogue": [], "enabled": {}, "log": []}
        # Presence in front of the mirror: None until the sensor has reported.
        self.presence = {"detected": None, "last_seen": None, "source": None}
        self.tuning = self.TUNING_DEFAULTS.copy()
        self.visibility = {"biometrics": True, "markets": True, "energy": True,
                          "calendar": True, "news": True, "weather": True}
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as fh:
                saved = json.load(fh)
            if isinstance(saved, dict):
                self.gate.update(saved)
                self.visibility.update(saved.get("visibility", {}))
                self.moments["enabled"].update(saved.get("moments_enabled", {}) or {})
                saved_tuning = saved.get("tuning", {}) or {}
                self.tuning.update({key: value for key, value in saved_tuning.items()
                                    if key in self.TUNING_DEFAULTS})
                # Preserve a profile made with the original shared biometric
                # controls when upgrading to independently tunable forms.
                for form in ("heart", "brain"):
                    for axis in ("x", "y", "scale"):
                        key = form + "_" + axis
                        legacy = "bio_" + axis
                        if key not in saved_tuning and legacy in saved_tuning:
                            self.tuning[key] = saved_tuning[legacy]
        except (FileNotFoundError, OSError, ValueError):
            pass

        # Reuse the existing single background HA fetcher. The old five-minute
        # display refresh missed motion and curtain transitions entirely.
        home = self.modules.get('smarthome')
        if home is not None:
            home.update_interval = timedelta(seconds=5)
            home.dashboard_update_interval = timedelta(seconds=5)
            from api_tracker import api_tracker
            api_tracker.set_limit('home-assistant', hourly=900, daily=20000)

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
        main_condition = (block.get("main") or "").lower()
        if "thunder" in main_condition:
            current_glyph = "storm"
        elif "rain" in main_condition or "drizzle" in main_condition:
            current_glyph = "rain"
        elif "cloud" in main_condition:
            current_glyph = "partly"
        else:
            current_glyph = "sun"
        out = {
            "temperature_c": int(round(temp)),
            "condition_label": (block.get("description") or "").capitalize(),
            "condition": main_condition,
            "glyph": current_glyph,
        }
        # Day/night is derived only when the provider supplied its actual
        # local sunrise and sunset timestamps.  Omitting it is preferable to
        # guessing from a clock or a forecast condition.
        sun = data.get('sys') or {}
        sunrise, sunset = _num(sun.get('sunrise')), _num(sun.get('sunset'))
        if sunrise is not None and sunset is not None:
            out['is_night'] = not (sunrise <= time.time() < sunset)
        # Preserve measured current conditions for the house scene.  Values
        # are omitted when the provider does not report them; the renderer
        # must never turn a forecast or a vague "rain" label into a storm.
        wind = _num((data.get('wind') or {}).get('speed'))
        if wind is not None:
            out['wind_mph'] = round(wind * 2.23694, 1)  # OpenWeather m/s
        rain_mm = _num((data.get('rain') or {}).get('1h'))
        if rain_mm is not None:
            out['rain_mm_h'] = rain_mm
        snow_mm = _num((data.get('snow') or {}).get('1h'))
        if snow_mm is not None:
            out['snow_mm_h'] = snow_mm

        # The sky is drawn from where the mirror actually is: the provider's
        # own coordinates let the page place the real sun and moon. Cloud
        # cover is the measured percentage, not inferred from a label.
        coord = data.get('coord') or data.get('coords') or {}
        lat, lon = _num(coord.get('lat')), _num(coord.get('lon'))
        if lat is not None and lon is not None:
            out['location'] = {'lat': round(lat, 3), 'lon': round(lon, 3)}
        cloud = _num((data.get('clouds') or {}).get('all'))
        if cloud is not None:
            out['cloud_pct'] = int(round(max(0, min(100, cloud))))

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

        # The next 24 hours of forecast temperature, for the sky's horizon
        # curve. Only hours the provider actually returned are included.
        curve = []
        for i in range(start, min(start + 24, len(times))):
            t = _num(temps[i]) if i < len(temps) else None
            if t is not None:
                curve.append({"at": times[i][11:16], "c": round(t, 1)})
        if len(curve) >= 6:
            out["curve"] = curve

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
                "color": list(ev.get("color") or (120, 180, 240)),
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
        index = getattr(mod, "current_index", 0) % len(heads)
        top = heads[index]
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
        for key in ('battery', 'cameras'):
            if live.get(key):
                out[key] = live[key]

        return out or None

    def _car(self, octo):
        """Actual charging is HA telemetry, never a planned Octopus slot."""
        out = {}
        charging = self._ha_boolean('car_charging_entity')
        if charging is not None:
            out['charging'] = charging

        # State of charge, if the account exposes it. Octopus does not
        # always return one, and a charge level is not something to
        # guess at, so the panel goes without when it is missing.
        prefs = getattr(octo, "charge_prefs", None) or {}
        soc = _num(self._ha_state(self.gate.get("car_soc_entity")))
        if soc is None:
            soc = _num(prefs.get("currentSoc", prefs.get("soc")))
        if soc is not None:
            out["charge_pct"] = int(round(soc))
        return out or None

    def _ha_boolean(self, key):
        value = str(self._ha_state(self.gate.get(key)) or '').lower()
        if value in ('on', 'occupied', 'home', 'charging', 'detected'):
            return True
        if value in ('off', 'clear', 'not_home', 'idle', 'discharging', 'not_charging'):
            return False
        return None

    # ---- Home Assistant -----------------------------------------------

    def _ha_states(self):
        mod = self.modules.get("smarthome")
        if mod is None:
            return {}
        all_states = getattr(mod, "_all_states", None)
        updated = getattr(mod, '_states_updated', None)
        if isinstance(updated, datetime) and (datetime.now() - updated).total_seconds() > 30:
            return {}  # stale motion must never remain active on the house
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

        living_occupancy = self._ha_state(self.gate.get("livingroom_occupancy_entity"))
        if living_occupancy is not None and str(living_occupancy).lower() not in ("unknown", "unavailable"):
            room_values.setdefault("livingroom", {})["occupied"] = str(living_occupancy).lower() in ("on", "occupied", "home")

        curtain = self._ha_state(self.gate.get("livingroom_curtain_entity"))
        if curtain is not None and str(curtain).lower() not in ("unknown", "unavailable"):
            room_values.setdefault("livingroom", {})["curtain"] = str(curtain).lower()
            row = self._ha_states().get(self.gate.get('livingroom_curtain_entity'), {})
            position = _num((row.get('attributes') or {}).get('current_position'))
            if position is not None:
                room_values['livingroom']['curtain_position'] = max(0, min(100, position))
        for room in ('livingroom', 'bedroom', 'upstairs'):
            value = self._ha_boolean(room + '_light_entity')
            if value is not None:
                room_values.setdefault(room, {})['light'] = value
        # Existing selected lights can be mapped only when their area is
        # explicit in the entity ID/friendly name. Never allocate a count
        # of lights to arbitrary windows or infer lights from occupancy.
        for room, names in (('livingroom', ('livingroom', 'living_room')),
                            ('bedroom', ('bedroom',)), ('upstairs', ('upstairs',))):
            if 'light' in room_values.get(room, {}):
                continue
            values = []
            for eid in lights:
                row = self._ha_states().get(eid, {})
                label = (eid + ' ' + str((row.get('attributes') or {}).get('friendly_name', ''))).lower().replace(' ', '_')
                if any(name in label for name in names) and row.get('state') in ('on', 'off'):
                    values.append(row['state'] == 'on')
            if values:
                room_values.setdefault(room, {})['light'] = any(values)
        for room, key in (('porch', 'doorbell_motion_entity'), ('external', 'external_motion_entity')):
            value = self._ha_boolean(key)
            if value is not None:
                room_values.setdefault(room, {})['occupied'] = value
        for room, key in (
            ('porch', 'porch_light_entity'), ('hallway', 'hall_light_entity'),
            ('bedroom1', 'bedroom1_light_entity'), ('bedroom2', 'bedroom2_light_entity'),
            ('bedroom3', 'bedroom3_light_entity'), ('bathroom', 'bathroom_light_entity'),
        ):
            value = self._ha_boolean(key)
            if value is not None:
                room_values.setdefault(room, {})['light'] = value
        living = room_values.setdefault('livingroom', {}) if any(
            self.gate.get(key) for key in ('livingroom_spotlights_entity', 'livingroom_led_entity')
        ) else None
        if living is not None:
            for field, key in (('spotlights', 'livingroom_spotlights_entity'), ('led', 'livingroom_led_entity')):
                value = self._ha_boolean(key)
                if value is not None:
                    living[field] = value
        devices = {}
        tv_state = str(self._ha_state(self.gate.get('livingroom_tv_entity')) or '').lower()
        if tv_state and tv_state not in ('unknown', 'unavailable'):
            devices['tv'] = tv_state not in ('off', 'standby', 'idle')
        alarm_state = self._ha_state(self.gate.get('alarm_entity'))
        if alarm_state is not None and str(alarm_state).lower() not in ('unknown', 'unavailable'):
            devices['alarm'] = str(alarm_state).lower()
        car_present = self._ha_boolean('car_presence_entity')
        if car_present is not None:
            devices['car_present'] = car_present
        upstairs_presence = self._ha_boolean('upstairs_occupancy_entity')
        if upstairs_presence is not None:
            room_values.setdefault('upstairs', {})['occupied'] = upstairs_presence
        front_door_open = self._ha_boolean('front_door_contact_entity')
        if front_door_open is not None:
            devices['front_door_open'] = front_door_open
        out['cameras'] = {name: bool(self.gate.get(name + '_camera_entity'))
                          for name in ('doorbell', 'external')}
        if devices:
            out['devices'] = devices
        soc = _num(self._ha_state(self.gate.get('battery_soc_entity')))
        if soc is not None:
            out['battery'] = {'charge_pct': max(0, min(100, soc))}
            charging = self._ha_boolean('battery_charging_entity')
            if charging is not None:
                out['battery']['charging'] = charging
        if room_values:
            out["rooms"] = room_values
        return out

    # ---- payload ------------------------------------------------------

    # ---- presence --------------------------------------------------------

    def _pir_state(self):
        """One small GET for the entrance sensor alone, with the smart-home
        module's own URL and credentials. The full-state poll every 5 s is too
        slow to wake the mirror as someone walks up to it."""
        entity = self.gate.get("entrance_pir_entity")
        home = self.modules.get("smarthome")
        url = getattr(home, "ha_url", "") if home else ""
        if not entity or not url:
            return None
        import requests
        try:
            resp = requests.get(f"{url}/api/states/{entity}", headers=home.headers, timeout=2)
            if resp.status_code != 200:
                return None
            state = str(resp.json().get("state", "")).lower()
        except Exception:
            return None
        if state in ("unknown", "unavailable", ""):
            return None
        return state in ("on", "detected", "occupied", "home", "motion")

    def poll_presence(self):
        detected = self._pir_state()
        if detected is None:
            return
        self._set_presence(detected, "pir")

    def _in_dim_hours(self):
        start, end = self.tuning.get("dim_start_hour", 2), self.tuning.get("dim_end_hour", 5)
        now = datetime.now()
        h = now.hour + now.minute / 60
        return (start <= h < end) if start <= end else (h >= start or h < end)

    def _maybe_unprompted(self, absent_seconds):
        """Someone arrived after a long absence: perhaps a pooled line.
        Never a new API call, never in the dim hours, never mid-turn."""
        resident = getattr(self, "resident", None)
        if resident is None or not self.tuning.get("resident_unprompted", 1):
            return
        if absent_seconds < self.tuning.get("resident_idle_minutes", 20) * 60 or self._in_dim_hours():
            return
        # Let the wake play first; the resident arrives into a woken glass.
        threading.Timer(2.5, resident.speak_unprompted).start()

    def _set_presence(self, detected, source):
        changed = detected != self.presence.get("detected")
        if detected and (changed or source == "manual"):
            self._maybe_unprompted(time.time() - (self.presence.get("last_seen") or 0))
        self.presence["detected"] = detected
        self.presence["source"] = source
        if detected:
            self.presence["last_seen"] = time.time()
        if changed or source == "manual":
            self.events.publish({"type": "presence", "detected": detected,
                                 "source": source, "at": time.time()})

    def ping_presence(self):
        """'I'm here' from the web panel: counts as a sighting, then lapses."""
        self._set_presence(True, "manual")
        return self.presence.copy()

    def snapshot(self):
        """The page payload. Only keys with real data behind them."""
        with self._lock:
            out = {"_live": True, "_events": True, "generated": int(time.time()),
                   "_visibility": self.visibility.copy(),
                   "_tuning": self.tuning.copy(),
                   "_moments": {"enabled": dict(self.moments["enabled"])}}
            if getattr(self, "resident", None) is not None:
                out["resident"] = {"available": True, "character": self.resident.profile.name,
                                   "key": self.resident.profile.key}
            configured = bool(self.gate.get("entrance_pir_entity"))
            if configured or self.presence.get("last_seen"):
                out["presence"] = {"configured": configured, **self.presence}
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
        calendar = self.modules.get("calendar")
        calendar_status = {"available": bool(calendar)}
        if calendar is not None:
            last_update = getattr(calendar, "last_update", None)
            calendar_status.update({
                "events": len(getattr(calendar, "events", []) or []),
                "parsed_events": len(calendar.parsed_events(4))
                    if callable(getattr(calendar, "parsed_events", None)) else 0,
                "credentials_configured": all(bool(getattr(calendar, "config", {}).get(k))
                                               for k in ("client_id", "client_secret", "refresh_token")),
                "fetch_in_flight": not getattr(calendar, "_fetcher", None).idle
                    if getattr(calendar, "_fetcher", None) is not None else False,
                "last_update": last_update.isoformat() if hasattr(last_update, "isoformat") else None,
                "last_error": getattr(calendar, "last_error", None),
            })
        return {
            "modules": {name: True for name in sorted(self.modules)},
            "configured_entities": {
                key: bool(value) for key, value in self.gate.items()
                if key.endswith("_entity") or key == "light_entities"
            },
            "entity_values": {
                key: value for key, value in self.gate.items()
                if key.endswith("_entity") or key == "light_entities"
            },
            "visibility": self.visibility.copy(),
            "tuning": self.tuning.copy(),
            "avatars": self._avatars(),
            "tickers": self._tickers(),
            "calendar": calendar_status,
            "resident": self.resident_status(),
            "moments": {"catalogue": self.moments["catalogue"],
                        "enabled": dict(self.moments["enabled"]),
                        "log": list(self.moments["log"])},
        }

    # ---- moments -------------------------------------------------------

    def moments_catalogue(self, items):
        clean = [{"name": str(i.get("name", ""))[:40], "label": str(i.get("label", ""))[:60],
                  "ambient": bool(i.get("ambient"))} for i in items if isinstance(i, dict) and i.get("name")]
        self.moments["catalogue"] = clean[:40]

    def moments_set_enabled(self, updates):
        names = {m["name"] for m in self.moments["catalogue"]}
        for key, value in updates.items():
            if key in names:
                self.moments["enabled"][key] = bool(value)
        self._persist_settings()
        return dict(self.moments["enabled"])

    def moments_play(self, name):
        self.events.publish({"type": "moment", "name": str(name)[:40]})

    def moments_played(self, name, reason):
        self.moments["log"].insert(0, {"name": str(name)[:40], "reason": str(reason)[:40],
                                       "at": datetime.now().strftime("%a %H:%M")})
        del self.moments["log"][30:]

    # ---- resident ------------------------------------------------------

    def resident_talk(self):
        if getattr(self, "resident", None) is None:
            raise RuntimeError("resident unavailable")
        self.resident.on_button_press()
        return {"recording": self.resident.recording}

    def resident_finished(self, token):
        if getattr(self, "resident", None) is not None:
            self.resident.player.finished(token)

    def resident_media(self, token):
        resident = getattr(self, "resident", None)
        return resident.media_path(token) if resident is not None else None

    def resident_unprompted_now(self):
        if getattr(self, "resident", None) is None:
            raise RuntimeError("resident unavailable")
        self.resident._last_unprompted = 0
        return {"clip": self.resident.speak_unprompted()}

    def resident_status(self):
        resident = getattr(self, "resident", None)
        if resident is None:
            return {"available": False}
        return {"available": True, "status": resident.status, "pool": resident.pool_summary(),
                "last_turn": resident.last_turn_summary(), "debug": resident.debug_snapshot()}

    def refresh_calendar(self):
        mod = self.modules.get("calendar")
        if mod is None or not hasattr(mod, "force_refresh"):
            return False
        return bool(mod.force_refresh())

    @staticmethod
    def _avatars():
        try:
            from avatar_profiles import AvatarProfiles
            return AvatarProfiles().options()
        except Exception as exc:
            logger.warning("avatar options unavailable: %s", exc)
            return []

    @staticmethod
    def avatar_reference(key):
        """The full reference portrait, by catalogue key only."""
        from avatar_profiles import AvatarProfiles
        try:
            path = AvatarProfiles().get(str(key)).reference_image
        except Exception:
            return None
        return str(path) if path.is_file() else None

    @staticmethod
    def avatar_thumb(key):
        """A small cached thumbnail of a character's reference image, for the
        control page. Looked up by catalogue key only - never by path - and
        made once with pygame (already loaded here); if that fails the
        original image is served instead."""
        from avatar_profiles import AvatarProfiles
        try:
            profile = AvatarProfiles().get(str(key))
        except Exception:
            return None
        source = profile.reference_image
        if not source.is_file():
            return None
        thumbs = os.path.join(PROJECT, "data", "avatar", "thumbs")
        target = os.path.join(thumbs, f"{profile.key}.png")
        try:
            if not os.path.isfile(target) or os.path.getmtime(target) < os.path.getmtime(source):
                import pygame
                os.makedirs(thumbs, exist_ok=True)
                image = pygame.image.load(str(source))
                w, h = image.get_size()
                scale = 320 / max(w, h)
                size = (max(1, int(w * scale)), max(1, int(h * scale)))
                try:
                    small = pygame.transform.smoothscale(image, size)
                except (ValueError, pygame.error):
                    # smoothscale needs a 24/32-bit image; a palette PNG
                    # still gets a thumbnail, just without the filtering.
                    small = pygame.transform.scale(image, size)
                pygame.image.save(small, target)
            return target
        except Exception as exc:
            logger.warning("avatar thumbnail failed for %s: %s", key, exc)
            return str(source)

    def select_avatar(self, key):
        # The running resident switches at once (and refuses mid-turn);
        # without one, the choice is persisted for the next start.
        if getattr(self, "resident", None) is not None:
            return self.resident.select_avatar(key).key
        from avatar_profiles import AvatarProfiles
        return AvatarProfiles().select(key).key

    def _tickers(self):
        mod = self.modules.get("stocks")
        return mod.get_tickers() if mod and hasattr(mod, "get_tickers") else []

    def set_tickers(self, symbols):
        mod = self.modules.get("stocks")
        if mod and hasattr(mod, "set_tickers"):
            mod.set_tickers(symbols)
        return self._tickers()

    def set_visibility(self, updates):
        for key, value in updates.items():
            if key in self.visibility:
                self.visibility[key] = bool(value)
        self._persist_settings()
        return self.visibility.copy()

    def _persist_settings(self):
        payload = {key: self.gate.get(key) for key in {
            "power_entity", "solar_entity", "car_soc_entity", "light_entities",
            "upstairs_temp_entity", "upstairs_humidity_entity", "downstairs_temp_entity",
            "downstairs_humidity_entity", "bedroom_occupancy_entity",
            "livingroom_occupancy_entity", "livingroom_curtain_entity",
        } | TWIN_ENTITIES}
        payload["visibility"] = self.visibility
        payload["moments_enabled"] = self.moments["enabled"]
        payload["tuning"] = self.tuning
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
                fh.write("\n")
        except OSError:
            logger.exception("could not persist visual-gate settings")

    def update_gate(self, updates):
        """Apply and persist non-secret visual-gate entity settings."""
        allowed = {
            "power_entity", "solar_entity", "car_soc_entity",
            "light_entities", "upstairs_temp_entity", "upstairs_humidity_entity",
            "downstairs_temp_entity", "downstairs_humidity_entity",
            "bedroom_occupancy_entity", "livingroom_occupancy_entity",
            "livingroom_curtain_entity",
        } | TWIN_ENTITIES
        clean = {}
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key == "light_entities":
                if isinstance(value, str):
                    value = [item.strip() for item in value.split(",") if item.strip()]
                if not isinstance(value, list):
                    continue
                clean[key] = [str(item).strip() for item in value if str(item).strip()]
            elif value is None:
                clean[key] = ""
            else:
                clean[key] = str(value).strip()
        self.gate.update(clean)
        self._persist_settings()
        return self.control_status()

    def update_tuning(self, updates):
        """Persist bounded visual controls; never treat them as HA entities."""
        limits = {
            "home_orbit_seconds": (18, 140), "home_orbit_angle": (15, 75),
            "home_orbit_pause": (0, 15), "home_camera_radius": (4.2, 9.0),
            "home_camera_height": (2.4, 6.5), "home_camera_fov": (20, 50),
            "home_target_x": (-1, 3.5), "home_target_y": (.25, 2.2),
            "home_target_z": (-.5, 2.5), "home_brightness": (0.4, 1.8),
            "home_stage_scale": (0.6, 1.4), "home_x": (-360, 360),
            "home_y": (-360, 360), "heart_x": (-420, 420), "heart_y": (-420, 420),
            "heart_scale": (0.55, 1.45), "brain_x": (-420, 420), "brain_y": (-420, 420),
            "brain_scale": (0.55, 1.45), "calendar_x": (-360, 360),
            "calendar_y": (-360, 360), "news_x": (-360, 360),
            "news_y": (-360, 360), "home_renderer": (0, 1),
            "rest_after_minutes": (1, 120), "dim_start_hour": (0, 23),
            "dim_end_hour": (0, 23), "dim_level": (0.1, 1.0),
            "resident_unprompted": (0, 1), "resident_idle_minutes": (2, 240),
            "moments_ambient": (0, 1), "ambient_gap_minutes": (2, 240),
            "ambient_daily_cap": (0, 50), "steps_goal": (1000, 50000),
            "market_surge_pct": (2, 50), "space_rocket_pct": (2, 50),
        }
        for key, value in updates.items():
            if key not in limits:
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value != value or value in (float("inf"), float("-inf")):
                continue
            lo, hi = limits[key]
            self.tuning[key] = max(lo, min(hi, value))
        self._persist_settings()
        return self.tuning.copy()


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

    def presence_loop():
        while True:
            try:
                bridge.poll_presence()
            except Exception:
                logger.exception("presence poll failed")
            time.sleep(1.0)

    threading.Thread(target=presence_loop, daemon=True, name="presence").start()

    import resident
    bridge.resident = resident.start(bridge.events.publish, bridge.tuning)
    if bridge.resident is not None:
        bridge.resident.set_context_sources(bridge.modules)
        logger.info("resident ready: %s", bridge.resident.profile.name)
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
