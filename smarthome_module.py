"""Smart Home module for AI-Mirror.

Displays Home Assistant entity states via the HA REST API (long-lived
access token), fetched as a single batched /api/states call on a
background thread.

Two display modes:
  - Mini view (always on, left column): summary line plus up to
    mini_entities entities with colored state dots.
  - Dashboard (on demand, center zone): all discovered entities grouped
    by domain, larger layout, faster refresh. Opened by voice command
    ("show the dashboard") or the 'h' key, auto-closes after
    dashboard_timeout seconds so the mirror stays a mirror.
"""

import math
import os
import requests
import pygame
import logging
import time
from datetime import datetime, timedelta
from config import (
    CONFIG, FONT_NAME, COLOR_FONT_DEFAULT, COLOR_FONT_BODY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM, COLOR_TITLE_BLUE,
    COLOR_ACCENT_GREEN, COLOR_ACCENT_RED, COLOR_ACCENT_AMBER,
    COLOR_ACCENT_BLUE, COLOR_ACCENT_TEAL, TRANSPARENCY,
)
from module_base import ModuleDrawHelper, SurfaceCache, InstrumentPanel
from effects_kit import draw_flare, glow_sprite
from api_tracker import api_tracker
from background_fetcher import BackgroundFetcher

logger = logging.getLogger("SmartHome")

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
# Web-panel entity selection: one entity_id per line. Takes precedence
# over HA_ENTITIES and auto-discovery when present.
_ENTITY_OVERRIDE = os.path.join(_PROJECT_DIR, 'data', 'smarthome_entities.txt')

# Domain-based state colors
DOMAIN_COLORS = {
    'light': {'on': COLOR_ACCENT_AMBER, 'off': COLOR_TEXT_SECONDARY},
    'switch': {'on': COLOR_ACCENT_GREEN, 'off': COLOR_TEXT_SECONDARY},
    'binary_sensor': {'on': COLOR_ACCENT_GREEN, 'off': COLOR_TEXT_SECONDARY},
    'lock': {'locked': COLOR_ACCENT_GREEN, 'unlocked': COLOR_ACCENT_RED},
    'alarm_control_panel': {'armed_home': COLOR_ACCENT_GREEN, 'armed_away': COLOR_ACCENT_GREEN,
                            'disarmed': COLOR_ACCENT_RED},
    'climate': {},
    'sensor': {},
    'cover': {'open': COLOR_ACCENT_AMBER, 'closed': COLOR_ACCENT_GREEN},
    'fan': {'on': COLOR_ACCENT_GREEN, 'off': COLOR_TEXT_SECONDARY},
    'media_player': {'playing': COLOR_ACCENT_GREEN, 'paused': COLOR_ACCENT_AMBER,
                     'idle': COLOR_TEXT_SECONDARY, 'off': COLOR_TEXT_SECONDARY},
}

# Dashboard section grouping by entity domain
DOMAIN_SECTIONS = [
    ('Lights', ('light',)),
    ('Climate', ('climate',)),
    ('Security', ('lock', 'alarm_control_panel')),
    ('Switches', ('switch',)),
    ('Covers & fans', ('cover', 'fan')),
    ('Media', ('media_player',)),
    ('Presence', ('person', 'device_tracker')),
    ('Sensors', ('sensor', 'binary_sensor')),
]


def _domain(entity_id):
    return entity_id.split('.')[0] if '.' in entity_id else ''


TOGGLE_DOMAINS = ('light', 'switch', 'lock', 'fan')


def _draw_toggle(screen, x, y, on, on_color, w=26, h=14):
    """A real toggle-switch pill -- on/off reads instantly without a
    status word, the way any phone settings screen shows it, instead of
    a colored dot that needs a text label next to it to mean anything."""
    track_color = on_color if on else (90, 92, 98)
    track = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(track, (*track_color, 130 if on else 90), track.get_rect(), border_radius=h // 2)
    pygame.draw.rect(track, (*track_color, 220), track.get_rect(), width=1, border_radius=h // 2)
    screen.blit(track, (x, y))
    r = h // 2 - 2
    cx = x + w - r - 2 if on else x + r + 2
    pygame.draw.circle(screen, (*track_color, 255), (cx, y + h // 2), r)


def _draw_shield_check(screen, cx, cy, color, size=9):
    """A small hand-drawn shield-with-checkmark glyph -- "all quiet" reads
    as reassurance rather than another line of text to parse."""
    pts = [
        (cx, cy - size), (cx + size * 0.8, cy - size * 0.6),
        (cx + size * 0.8, cy + size * 0.3), (cx, cy + size),
        (cx - size * 0.8, cy + size * 0.3), (cx - size * 0.8, cy - size * 0.6),
    ]
    pygame.draw.polygon(screen, color, pts, 1)
    pygame.draw.lines(screen, color, False, [
        (cx - size * 0.35, cy), (cx - size * 0.05, cy + size * 0.3), (cx + size * 0.4, cy - size * 0.35),
    ], 2)


def _state_color(entity_id, state, attrs=None):
    """Pick a display color based on entity domain and state."""
    domain = _domain(entity_id)
    attrs = attrs or {}
    device_class = attrs.get('device_class')
    # An "on" contact sensor means a door/window is open, not healthy.
    if domain == 'binary_sensor' and state == 'on':
        if device_class in ('door', 'window', 'garage_door', 'opening', 'moisture', 'smoke', 'gas', 'safety'):
            return COLOR_ACCENT_RED
    domain_map = DOMAIN_COLORS.get(domain, {})
    if state in domain_map:
        return domain_map[state]

    # Temperature-like sensors: color by value
    if domain in ('sensor', 'climate'):
        try:
            val = float(state)
            if val < 10:
                return COLOR_ACCENT_BLUE
            if val > 28:
                return COLOR_ACCENT_RED
            return COLOR_FONT_BODY
        except (ValueError, TypeError):
            pass

    # Unavailable / unknown
    if state in ('unavailable', 'unknown'):
        return COLOR_ACCENT_RED

    return COLOR_FONT_BODY


def _friendly_state(entity_id, info, max_len=24):
    """Turn HA's machine-oriented state into a glanceable mirror value."""
    state = str(info.get('state', '?'))
    attrs = info.get('attributes', {}) or {}
    domain = _domain(entity_id)
    device_class = attrs.get('device_class', '')
    unit = str(attrs.get('unit_of_measurement', '') or '')

    if state in ('unavailable', 'unknown', 'none'):
        return 'Unavailable'
    if domain == 'binary_sensor':
        labels = {
            'door': ('Closed', 'OPEN'), 'window': ('Closed', 'OPEN'),
            'garage_door': ('Closed', 'OPEN'), 'opening': ('Closed', 'OPEN'),
            'motion': ('Clear', 'Motion'), 'occupancy': ('Clear', 'Occupied'),
            'presence': ('Away', 'Home'), 'moisture': ('Dry', 'WET'),
            'smoke': ('Clear', 'SMOKE'), 'gas': ('Clear', 'GAS'),
            'safety': ('Safe', 'ALERT'), 'battery': ('OK', 'Low battery'),
        }
        off, on = labels.get(device_class, ('Off', 'On'))
        return on if state == 'on' else off if state == 'off' else state.replace('_', ' ').title()
    if domain == 'light':
        if state != 'on': return 'Off'
        brightness = attrs.get('brightness')
        if isinstance(brightness, (int, float)):
            return f"On {round(brightness / 255 * 100)}%"
        return 'On'
    if domain == 'cover':
        position = attrs.get('current_position')
        if isinstance(position, (int, float)) and state not in ('closed', 'closing'):
            return f"Open {round(position)}%"
        return state.replace('_', ' ').title()
    if domain == 'climate':
        current = attrs.get('current_temperature')
        target = attrs.get('temperature')
        suffix = '°C' if unit in ('°C', 'C') else unit
        if current is not None and target is not None:
            return f"{current}{suffix} -> {target}{suffix}"
        if current is not None: return f"{current}{suffix}"
        return state.replace('_', ' ').title()
    if domain == 'media_player' and state == 'playing':
        title = attrs.get('media_title') or attrs.get('media_channel')
        return f"Playing: {title}" if title else 'Playing'
    if domain in ('person', 'device_tracker'):
        return 'Home' if state == 'home' else state.replace('_', ' ').title()
    if state in ('on', 'off'):
        return state.title()
    value = f"{state}{unit}" if unit else state.replace('_', ' ').title()
    return value if len(value) <= max_len else value[:max_len - 2].rstrip() + '..'


class SmartHomeModule(InstrumentPanel):
    def __init__(self, ha_url, ha_token, entities=None,
                 update_interval_minutes=2, timeout=10,
                 max_entities=20, mini_entities=8,
                 dashboard_timeout=60, max_candidates=45,
                 presence_entities=None, **kwargs):
        # Prepend scheme if missing - requests needs http:// or it raises
        # "No connection adapters were found"
        ha_url = (ha_url or '').strip().rstrip('/')
        if ha_url and not ha_url.startswith(('http://', 'https://')):
            ha_url = 'http://' + ha_url
        self.ha_url = ha_url
        self.ha_token = ha_token or ''
        self.headers = {
            "Authorization": f"Bearer {self.ha_token}",
            "content-type": "application/json",
        }
        self.entities = entities or []
        # Web-panel selection file wins over HA_ENTITIES / auto-discovery
        file_ents = self._load_entity_override()
        self._manual_entity_override = bool(file_ents)
        self._motion_override_fallback = False
        if file_ents:
            self.entities = file_ents
        self.max_entities = max_entities
        self.mini_entities = mini_entities
        self.max_candidates = max_candidates
        self._candidates = []   # scored pool for the web panel checklist
        self.data = {}
        self.last_update = datetime.min
        # Presence is kept separately from the display selection so the
        # overnight power-saving rule never depends on a person entity being
        # visible in the dashboard.
        self.presence_entities = list(presence_entities or [])
        self._presence_states = {}
        self._presence_updated = datetime.min
        self._all_states = []
        self._states_updated = datetime.min
        self.update_interval = timedelta(minutes=update_interval_minutes)
        self.dashboard_update_interval = timedelta(seconds=60)
        self.timeout = timeout
        self._connected = False
        self._last_error = None
        self._surface_cache = SurfaceCache()
        self._last_data_hash = None
        self._notification_callback = None
        self._moment_callback = None
        self._lights_were_on = False
        self._fetcher = BackgroundFetcher("smarthome")

        # Dashboard overlay state
        self.dashboard_active = False
        self.dashboard_timeout = dashboard_timeout
        self._dashboard_until = 0.0
        self._dash_alpha = 0.0
        self._last_tick = time.monotonic()

        # Fonts are lazy-initialised on first draw
        self.title_font = None
        self.body_font = None
        self.small_font = None

    def set_notification_callback(self, callback):
        """Allow main app to wire center notifications."""
        self._notification_callback = callback

    def set_moment_callback(self, callback):
        """Register a callback for Director moment triggers (event_director.py)."""
        self._moment_callback = callback

    # ------------------------------------------------------------------
    # Dashboard control (voice command / keyboard)
    # ------------------------------------------------------------------

    def show_dashboard(self):
        if not self.ha_url:
            return
        self.dashboard_active = True
        self._dashboard_until = time.monotonic() + self.dashboard_timeout
        logger.info("HA dashboard opened")

    def hide_dashboard(self):
        if self.dashboard_active:
            logger.info("HA dashboard closed")
        self.dashboard_active = False

    def toggle_dashboard(self):
        if self.dashboard_active:
            self.hide_dashboard()
        else:
            self.show_dashboard()

    # ------------------------------------------------------------------
    # Web-panel entity selection
    # ------------------------------------------------------------------

    def _load_entity_override(self):
        try:
            if not os.path.exists(_ENTITY_OVERRIDE):
                return []
            with open(_ENTITY_OVERRIDE, 'r', encoding='utf-8') as f:
                ents = [ln.strip() for ln in f if ln.strip()]
            if ents:
                logger.info(f"Loaded {len(ents)} HA entities from override file")
            return ents
        except Exception as e:
            logger.warning(f"Could not read entity override: {e}")
            return []

    def _save_entity_override(self, entities):
        try:
            os.makedirs(os.path.dirname(_ENTITY_OVERRIDE), exist_ok=True)
            if not entities:
                if os.path.exists(_ENTITY_OVERRIDE):
                    os.remove(_ENTITY_OVERRIDE)
                return
            tmp = _ENTITY_OVERRIDE + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write("\n".join(entities) + "\n")
            os.replace(tmp, _ENTITY_OVERRIDE)
        except Exception as e:
            logger.warning(f"Could not save entity override: {e}")

    def get_entity_options(self):
        """For the web panel: candidate entities with which are shown.

        Returns [{id, name, state, shown}], currently-shown first (so they
        are easy to untick) then the rest of the scored candidate pool.
        """
        shown = list(self.entities)
        shown_set = set(shown)
        options, seen = [], set()
        for eid in shown:
            cand = next((c for c in self._candidates if c['id'] == eid), {})
            options.append({
                'id': eid,
                'name': cand.get('name', eid),
                'state': self.data.get(eid, {}).get('state', cand.get('state', '?')),
                'shown': True,
            })
            seen.add(eid)
        for c in self._candidates:
            if c['id'] in seen:
                continue
            options.append({
                'id': c['id'], 'name': c['name'],
                'state': c['state'], 'shown': c['id'] in shown_set,
            })
        return options

    def set_entities(self, ids):
        """Replace shown entities from the web panel and persist.

        Runs on the main loop (command queue). Empty list clears the
        override file and restores auto-discovery.
        """
        seen = set()
        valid = []
        for e in ids:
            e = (e or '').strip()
            if e and e not in seen:
                seen.add(e)
                valid.append(e)

        self.data = {k: v for k, v in self.data.items() if k in seen}
        self._save_entity_override(valid)
        if valid:
            self.entities = valid
            logger.info(f"HA entities set via web panel: {valid}")
        else:
            self.entities = []   # auto-discovery resumes on next fetch
            logger.info("HA entity selection cleared; auto-discovery restored")
        self.last_update = datetime.min  # force an immediate refresh
        return True

    # ------------------------------------------------------------------
    # Data fetch (background thread)
    # ------------------------------------------------------------------

    def _fetch_states_blocking(self):
        """Fetch ALL entity states in one /api/states call (background thread)."""
        url = f"{self.ha_url}/api/states"
        try:
            resp = requests.get(url, headers=self.headers, timeout=self.timeout)
            resp.raise_for_status()
        except Exception:
            api_tracker.failure("smarthome", "home-assistant")
            raise
        api_tracker.record("smarthome", "home-assistant")
        return resp.json()

    # Domains worth showing on a mirror, with a base usefulness score
    _DOMAIN_SCORE = {
        'lock': 10, 'alarm_control_panel': 10, 'climate': 9,
        'light': 7, 'binary_sensor': 6, 'switch': 5, 'sensor': 4,
        'cover': 6, 'fan': 5, 'media_player': 5, 'person': 8, 'device_tracker': 6,
    }
    # device_class bonus (real home state people glance at)
    _DC_SCORE = {
        'temperature': 9, 'humidity': 7, 'door': 9, 'window': 9, 'garage_door': 9,
        # Motion is useful as an alert, not as the main thing a person sees
        # while standing at the mirror. Keep it available but rank it low.
        'motion': 1, 'occupancy': 3, 'presence': 8, 'moisture': 7,
        'power': 6, 'energy': 6, 'gas': 6, 'co2': 6, 'pm25': 5, 'battery': 3,
    }
    # device_class values that are noise on a mirror
    _SKIP_DC = ('timestamp', 'date', 'enum', 'update', 'connectivity', 'problem')
    # name fragments that mark system/diagnostic sensors
    _NOISE = ('snapshot', '_path', 'backup', 'sun_next', 'uptime', 'version',
              'scheduled', 'last_attempted', 'last_successful')

    def _score_states(self, all_states):
        """Return useful entities as sorted [(score, eid, attrs)], best first.

        Skips diagnostic/config entities, system sensors (backup, sun,
        snapshots, updates) and string sensors with no unit.
        """
        scored = []
        for s in all_states:
            eid = s.get('entity_id', '')
            domain = eid.split('.')[0] if '.' in eid else ''
            base = self._DOMAIN_SCORE.get(domain)
            if base is None:
                continue

            attrs = s.get('attributes', {})
            if attrs.get('entity_category') in ('diagnostic', 'config'):
                continue

            name = (attrs.get('friendly_name') or eid).lower()
            if any(frag in eid.lower() or frag in name for frag in self._NOISE):
                continue

            dc = attrs.get('device_class')
            if domain == 'sensor':
                # Keep only real measurements: a unit, or a useful class.
                # Drops snapshot-path / status-string / counter sensors.
                if dc in self._SKIP_DC:
                    continue
                if not attrs.get('unit_of_measurement') and dc not in self._DC_SCORE:
                    continue

            score = base + self._DC_SCORE.get(dc, 0)
            scored.append((score, eid, attrs))

        scored.sort(key=lambda x: (-x[0], x[1]))
        return scored

    def _pick_entities(self, scored):
        """Auto-discover: take the top-scoring entities up to max_entities."""
        picked = [eid for _, eid, _ in scored[:self.max_entities]]
        if picked:
            self.entities = picked
            logger.info(f"Auto-discovered {len(picked)} HA entities: {picked}")
        else:
            logger.warning("Auto-discovery found no suitable entities")

    def _apply_states(self, all_states):
        current_time = datetime.now()
        self._all_states = list(all_states)
        self._states_updated = current_time
        by_id = {s.get('entity_id'): s for s in all_states}

        # Prefer an explicit HA_PRESENCE_ENTITIES list. Without one, use only
        # Home Assistant's person.* entities (not arbitrary device trackers),
        # which is the conservative choice for an unattended display.
        presence_ids = self.presence_entities or sorted(
            entity_id for entity_id in by_id if _domain(entity_id) == 'person'
        )
        self._presence_states = {
            entity_id: str(by_id.get(entity_id, {}).get('state', 'unknown')).lower()
            for entity_id in presence_ids
        }
        self._presence_updated = current_time

        # Refresh the candidate pool the web panel offers to toggle
        scored = self._score_states(all_states)
        self._candidates = [
            {
                'id': eid,
                'name': attrs.get('friendly_name', eid),
                'state': by_id.get(eid, {}).get('state', '?'),
                'unit': attrs.get('unit_of_measurement', ''),
            }
            for _, eid, attrs in scored[:self.max_candidates]
        ]

        # Older web-panel selections can accidentally contain only motion
        # sensors. Do not delete the user's file, but use a useful temporary
        # cross-section for this running display instead of a motion wall.
        selected_states = [by_id.get(eid, {}) for eid in self.entities]
        only_motion = bool(selected_states) and all(
            _domain(eid) == 'binary_sensor'
            and state.get('attributes', {}).get('device_class') == 'motion'
            for eid, state in zip(self.entities, selected_states)
        )
        if self._manual_entity_override and only_motion and not self._motion_override_fallback:
            replacement = [eid for _, eid, attrs in scored
                           if not (_domain(eid) == 'binary_sensor' and attrs.get('device_class') == 'motion')]
            if replacement:
                self.entities = replacement[:self.max_entities]
                self._motion_override_fallback = True
                logger.warning("HA entity override contained only motion sensors; using useful auto-selection for this session")

        if not self.entities:
            self._pick_entities(scored)
            if not self.entities:
                self._last_error = "No entities found"
                return

        old_states = {eid: self.data.get(eid, {}).get('state') for eid in self.entities}

        for entity_id in self.entities:
            state = by_id.get(entity_id)
            if state is not None:
                self.data[entity_id] = {
                    'state': state.get('state', 'unknown'),
                    'attributes': state.get('attributes', {}),
                    'last_updated': current_time,
                    'status': 'ok',
                }
            else:
                self.data[entity_id] = {
                    'state': 'unavailable',
                    'attributes': self.data.get(entity_id, {}).get('attributes', {}),
                    'last_updated': current_time,
                    'status': 'error',
                }

        self._connected = True
        self._last_error = None

        # Push notification if a notable state changed
        if self._notification_callback or self._moment_callback:
            for eid in self.entities:
                old = old_states.get(eid)
                new = self.data.get(eid, {}).get('state')
                if old and new and old != new:
                    if _domain(eid) in ('lock', 'alarm_control_panel'):
                        name = self.data[eid].get('attributes', {}).get('friendly_name', eid)
                        if self._notification_callback:
                            self._notification_callback(
                                f"{name}: {new}",
                                COLOR_ACCENT_AMBER, 5000
                            )
                        if self._moment_callback and new in ('locked', 'armed_home', 'armed_away'):
                            self._moment_callback('house_armed', {'name': name})
                    elif (self._moment_callback and old == 'off' and new == 'on'
                          and _domain(eid) == 'binary_sensor'
                          and self.data[eid].get('attributes', {}).get('device_class') == 'motion'):
                        name = self.data[eid].get('attributes', {}).get('friendly_name', eid)
                        self._moment_callback('motion_detected', {'name': name, 'side': 'left'})

        # A whole-house "all lights off" moment fires once on the
        # transition, not every update cycle while it stays dark.
        if self._moment_callback:
            light_states = [self.data.get(eid, {}).get('state')
                            for eid in self.entities if _domain(eid) == 'light']
            lights_on_now = any(s == 'on' for s in light_states)
            if self._lights_were_on and not lights_on_now and light_states:
                self._moment_callback('all_lights_off', None)
            self._lights_were_on = lights_on_now

    def everyone_away(self, max_age_seconds=300):
        """Return True only when fresh HA presence data confirms everyone away.

        False means someone is present. None is deliberately fail-safe: HA is
        unavailable, stale, unconfigured, or has no usable presence entities.
        """
        if not self._connected or not self._presence_states:
            return None
        if (datetime.now() - self._presence_updated).total_seconds() > max_age_seconds:
            return None
        states = tuple(self._presence_states.values())
        if any(state in ('home', 'on', 'occupied', 'present') for state in states):
            return False
        if all(state in ('away', 'not_home', 'off', 'unavailable') for state in states):
            return True
        return None

    def states_snapshot(self, max_age_seconds=600):
        """Fresh raw HA state snapshot for another local mirror module.

        This prevents Phone and Smart Home both polling `/api/states` for the
        same data. Nothing is copied off-device or sent to another service.
        """
        if not self._connected or not self._all_states:
            return None
        if (datetime.now() - self._states_updated).total_seconds() > max_age_seconds:
            return None
        return self._all_states, self._states_updated

    def update(self):
        # Dashboard housekeeping: auto-close and fade
        now = time.monotonic()
        dt = min(now - self._last_tick, 0.1)
        self._last_tick = now
        if self.dashboard_active and now > self._dashboard_until:
            self.hide_dashboard()
        target = 1.0 if self.dashboard_active else 0.0
        step = 3.0 * dt
        self._dash_alpha += max(-step, min(step, target - self._dash_alpha))

        if not self.ha_url or not self.ha_token:
            self._last_error = "No HA URL or token configured"
            self._connected = False
            return

        result = self._fetcher.take_result()
        if result is not None:
            ok, value = result
            if ok:
                self._apply_states(value)
            else:
                logger.warning(f"HA fetch failed: {value}")
                self._connected = False
                self._last_error = str(value)
            self.last_update = datetime.now()

        # Refresh faster while someone is looking at the dashboard
        interval = (self.dashboard_update_interval if self.dashboard_active
                    else self.update_interval)
        if datetime.now() - self.last_update < interval:
            return
        if not api_tracker.allow("smarthome", "home-assistant"):
            # Blocked (rate limit or open circuit): wait a full interval
            # before retrying instead of hammering allow() every frame
            self.last_update = datetime.now()
            return
        self._fetcher.submit(self._fetch_states_blocking)

    # ------------------------------------------------------------------
    # Shared draw helpers
    # ------------------------------------------------------------------

    def _ensure_fonts(self):
        if self.title_font is None:
            title_f, body_f, small_f = ModuleDrawHelper.get_fonts()
            self.title_font = title_f
            self.body_font = body_f
            self.small_font = small_f

    def _entity_label(self, entity_id, max_len=16):
        info = self.data.get(entity_id, {})
        name = info.get('attributes', {}).get('friendly_name', entity_id)
        if len(name) > max_len:
            name = name[:max_len].rstrip() + '..'
        return name

    def _entity_state_text(self, entity_id, max_len=20):
        info = self.data.get(entity_id, {})
        return _friendly_state(entity_id, info, max_len=max_len)

    def _entity_color(self, entity_id):
        info = self.data.get(entity_id, {})
        return _state_color(entity_id, info.get('state', '?'), info.get('attributes', {}))

    def _open_security_entities(self):
        """Return open/unlocked security items first; these deserve attention."""
        alerts = []
        for eid in self.entities:
            info = self.data.get(eid, {})
            state = info.get('state')
            domain = _domain(eid)
            dc = info.get('attributes', {}).get('device_class')
            if domain == 'lock' and state == 'unlocked':
                alerts.append(eid)
            elif domain == 'binary_sensor' and state == 'on' and dc in (
                'door', 'window', 'garage_door', 'opening', 'moisture', 'smoke', 'gas', 'safety'
            ):
                alerts.append(eid)
        return alerts

    def _summary_text(self):
        """One-line rollup for the mini view, e.g. '3 on - 21.4C'."""
        parts = []
        on_count = sum(
            1 for eid in self.entities
            if _domain(eid) in ('light', 'switch')
            and self.data.get(eid, {}).get('state') == 'on'
        )
        if on_count:
            parts.append(f"{on_count} light{'s' if on_count != 1 else ''} on")
        for eid in self.entities:
            if _domain(eid) in ('climate', 'sensor'):
                info = self.data.get(eid, {})
                unit = info.get('attributes', {}).get('unit_of_measurement', '')
                current = info.get('attributes', {}).get('current_temperature')
                if current is not None:
                    parts.append(f"{current}°C")
                    break
                if 'C' in unit or 'F' in unit:
                    parts.append(_friendly_state(eid, info))
                    break
        alerts = self._open_security_entities()
        if alerts:
            parts.append(f"{len(alerts)} SECURITY ALERT" if len(alerts) > 1 else "SECURITY ALERT")
        else:
            locked = [eid for eid in self.entities if _domain(eid) == 'lock']
            if locked:
                parts.append("secure" if all(self.data.get(eid, {}).get('state') == 'locked' for eid in locked) else "check locks")
        playing = [eid for eid in self.entities if _domain(eid) == 'media_player' and self.data.get(eid, {}).get('state') == 'playing']
        if playing:
            parts.append("media playing")
        return "  |  ".join(parts)

    # ------------------------------------------------------------------
    # Mini view (left column)
    # ------------------------------------------------------------------

    def _habitat_groups(self):
        """Sort the shown entities into the systems the panel reports on."""
        groups = {'security': [], 'motion': [], 'climate': [],
                  'lighting': [], 'other': []}
        for eid in self.entities:
            info = self.data.get(eid)
            if not info:
                continue
            domain = _domain(eid)
            dc = (info.get('attributes') or {}).get('device_class')
            if domain in ('lock', 'alarm_control_panel'):
                groups['security'].append(eid)
            elif domain == 'binary_sensor' and dc in (
                    'door', 'window', 'garage_door', 'opening',
                    'moisture', 'smoke', 'gas', 'safety'):
                groups['security'].append(eid)
            elif domain == 'binary_sensor' and dc in ('motion', 'occupancy', 'presence'):
                groups['motion'].append(eid)
            elif domain == 'climate' or (
                    domain == 'sensor' and dc in ('temperature', 'humidity')):
                groups['climate'].append(eid)
            elif domain in ('light', 'switch', 'fan'):
                groups['lighting'].append(eid)
            else:
                groups['other'].append(eid)
        return groups

    @staticmethod
    def _sensor_value(info):
        attrs = info.get('attributes') or {}
        for key in ('current_temperature', 'temperature'):
            if isinstance(attrs.get(key), (int, float)):
                return float(attrs[key])
        try:
            return float(info.get('state'))
        except (TypeError, ValueError):
            return None

    def draw(self, screen, position):
        """HABITAT: dwelling systems status."""
        self.draw_instrument(screen, position, default=(300, 300))

    def _render_panel(self, surf, width, height, position=None):
        import theme
        accent = theme.module_accent('smarthome')
        pad = 6
        ix, iw = pad, width - pad * 2

        groups = self._habitat_groups() if self.data else None
        alerts = self._open_security_entities() if self.data else []
        secure = not alerts
        status_text = "SECURE" if secure else f"{len(alerts)} ALERT"
        status_color = COLOR_ACCENT_GREEN if secure else COLOR_ACCENT_RED

        zones = len(self.entities) if self.entities else 0
        cur = self._panel_header(
            surf, ix, 0, iw, "Habitat", accent,
            subtitle=f"{zones} NODES LINKED" if zones else None,
            right_text=status_text, right_color=status_color)

        if not self.ha_url or not self.ha_token:
            msg = self._text('f_small', "HA NOT CONFIGURED", COLOR_TEXT_SECONDARY, spacing=1)
            surf.blit(msg, (ix, cur + 8))
            return
        if not self.data:
            msg = self._text('f_small',
                             "LINK ERROR" if self._last_error else "LINKING...",
                             COLOR_TEXT_SECONDARY, spacing=1)
            surf.blit(msg, (ix, cur + 8))
            return

        remaining = height - cur
        peri_h = int(min(210, remaining * 0.44))
        cur = self._draw_perimeter(surf, ix, cur, iw, peri_h, accent, groups, alerts)

        cur = self._draw_climate(surf, ix, cur + 8, iw, accent, groups['climate'], height)
        cur = self._draw_lighting(surf, ix, cur + 10, iw, accent, groups['lighting'], height)
        cur = self._draw_systems(surf, ix, cur + 10, iw, accent, groups['other'], height)

        if self._last_error and cur < height - 12:
            err = self._text('f_nano', "LINK DEGRADED", COLOR_ACCENT_RED, spacing=1)
            surf.blit(err, (ix, height - 11))

    def _draw_perimeter(self, surf, x, y, w, h, accent, groups, alerts):
        """A dwelling outline with live perimeter markers -- the security
        picture as a diagram rather than a list of door names."""
        t = pygame.time.get_ticks() / 1000.0
        hw = min(w * 0.30, h * 0.52)
        hh = h * 0.74
        cx = x + w * 0.50
        top = y + 8

        roof_y = top + hh * 0.32
        wall_hw = hw * 0.86
        wall_bottom = top + hh

        pygame.draw.lines(surf, (*accent, 200), False, [
            (cx - hw, roof_y), (cx, top), (cx + hw, roof_y)], 2)
        pygame.draw.rect(surf, (*accent, 22),
                         (int(cx - wall_hw), int(roof_y),
                          int(wall_hw * 2), int(wall_bottom - roof_y)))
        pygame.draw.rect(surf, (*accent, 200),
                         (int(cx - wall_hw), int(roof_y),
                          int(wall_hw * 2), int(wall_bottom - roof_y)), 2)
        pygame.draw.line(surf, (*accent, 70),
                         (cx - hw * 1.25, wall_bottom), (cx + hw * 1.25, wall_bottom), 1)

        door_w, door_h = wall_hw * 0.30, (wall_bottom - roof_y) * 0.42
        pygame.draw.rect(surf, (*accent, 150),
                         (int(cx - door_w / 2), int(wall_bottom - door_h),
                          int(door_w), int(door_h)), 1)

        # Storey division and window openings give the shell some depth
        floor_y = roof_y + (wall_bottom - roof_y) * 0.52
        pygame.draw.line(surf, (*accent, 60),
                         (cx - wall_hw, floor_y), (cx + wall_hw, floor_y), 1)
        win_w = wall_hw * 0.26
        win_h = (wall_bottom - roof_y) * 0.20
        for fx in (-0.52, 0.52):
            for fy in (0.16, 0.62):
                wx = cx + wall_hw * fx - win_w / 2
                wy = roof_y + (wall_bottom - roof_y) * fy
                pygame.draw.rect(surf, (*accent, 95),
                                 (int(wx), int(wy), int(win_w), int(win_h)), 1)

        # Interior occupancy dots pulse when a motion sensor is live
        motion_active = [e for e in groups['motion']
                         if self.data.get(e, {}).get('state') == 'on']
        spots = [(-0.45, 0.30), (0.45, 0.30), (-0.45, 0.68), (0.45, 0.68)]
        for i, (fx, fy) in enumerate(spots):
            px = cx + wall_hw * fx
            py = roof_y + (wall_bottom - roof_y) * fy
            live = i < len(motion_active)
            if live:
                pulse = 0.5 + 0.5 * math.sin(t * 4.0 + i)
                pygame.draw.circle(surf, (*COLOR_ACCENT_AMBER, int(90 + 150 * pulse)),
                                   (int(px), int(py)), 4)
            else:
                pygame.draw.circle(surf, (*accent, 70), (int(px), int(py)), 3, 1)

        # Perimeter markers: one per security entity, placed on the outline
        anchors = [
            (cx - wall_hw, roof_y + (wall_bottom - roof_y) * 0.35),
            (cx + wall_hw, roof_y + (wall_bottom - roof_y) * 0.35),
            (cx - wall_hw, roof_y + (wall_bottom - roof_y) * 0.72),
            (cx + wall_hw, roof_y + (wall_bottom - roof_y) * 0.72),
            (cx, wall_bottom),
            (cx, roof_y),
        ]
        for i, eid in enumerate(groups['security'][:len(anchors)]):
            ax, ay = anchors[i]
            open_now = eid in alerts
            color = COLOR_ACCENT_RED if open_now else COLOR_ACCENT_GREEN
            if open_now:
                pulse = 0.5 + 0.5 * math.sin(t * 5.0)
                halo = glow_sprite(9, color, int(60 + 90 * pulse), core_frac=0.25)
                surf.blit(halo, (ax - halo.get_width() / 2, ay - halo.get_height() / 2))
            pygame.draw.rect(surf, (*color, 240), (int(ax - 3), int(ay - 3), 6, 6))

        # Status block beside the house
        sx = x
        sy = y + 10
        if alerts:
            head = self._text('f_micro', "BREACH", COLOR_ACCENT_RED, spacing=2)
            surf.blit(head, (sx, sy))
            sy += head.get_height() + 3
            for eid in alerts[:3]:
                nm = self._text('f_nano', self._entity_label(eid, 14).upper(),
                                COLOR_ACCENT_RED, spacing=1)
                surf.blit(nm, (sx, sy))
                sy += nm.get_height() + 2
        else:
            _draw_shield_check(surf, sx + 8, sy + 8, COLOR_ACCENT_GREEN, size=8)
            head = self._text('f_nano', "PERIMETER", COLOR_TEXT_DIM, spacing=1)
            surf.blit(head, (sx, sy + 20))
            val = self._text('f_nano', "SEALED", COLOR_ACCENT_GREEN, spacing=1)
            surf.blit(val, (sx, sy + 20 + head.get_height() + 1))

        quiet = len(groups['motion']) - len(motion_active)
        rx = x + w
        ry = y + 10
        occ_lbl = self._text('f_nano', "OCCUPANCY", COLOR_TEXT_DIM, spacing=1)
        surf.blit(occ_lbl, (rx - occ_lbl.get_width(), ry))
        occ_val = self._text(
            'f_nano',
            f"{len(motion_active)} ACTIVE" if motion_active else f"{quiet} QUIET",
            COLOR_ACCENT_AMBER if motion_active else COLOR_ACCENT_GREEN, spacing=1)
        surf.blit(occ_val, (rx - occ_val.get_width(), ry + occ_lbl.get_height() + 1))
        return y + h

    def _draw_climate(self, surf, x, y, w, accent, entities, height):
        from effects_kit import draw_bar_meter
        if not entities:
            return y
        lbl = self._text('f_nano', "CLIMATE", accent, spacing=2)
        surf.blit(lbl, (x, y))
        cur = y + lbl.get_height() + 4

        for eid in entities[:3]:
            if cur + 20 > height:
                break
            info = self.data.get(eid, {})
            value = self._sensor_value(info)
            attrs = info.get('attributes') or {}
            unit = str(attrs.get('unit_of_measurement', '') or '')
            name = self._text('f_nano', self._entity_label(eid, 13).upper(),
                              COLOR_TEXT_SECONDARY, spacing=1)
            surf.blit(name, (x, cur))
            if value is None:
                cur += 18
                continue
            if '%' in unit:
                frac = max(0.0, min(1.0, value / 100.0))
                shown = f"{value:.0f}%"
            else:
                frac = max(0.0, min(1.0, (value - 5.0) / 25.0))
                shown = f"{value:.1f}C"
            val = self._text('f_small', shown, COLOR_FONT_BODY)
            surf.blit(val, (x + w - val.get_width(), cur - 2))
            bar_x = x + 86
            bar_w = w - 86 - val.get_width() - 8
            if bar_w > 20:
                draw_bar_meter(surf, bar_x, cur + 2, bar_w, 6, frac, accent,
                               segments=max(6, int(bar_w / 9)))
            cur += 18
        return cur

    def _draw_systems(self, surf, x, y, w, accent, entities, height):
        """Whatever else is linked -- media, presence, covers. Compact
        rows, value-first, no repeated entity-name-colon-state sentences."""
        if not entities or y + 24 > height:
            return y
        lbl = self._text('f_nano', "SYSTEMS", accent, spacing=2)
        surf.blit(lbl, (x, y))
        cur = y + lbl.get_height() + 4
        for eid in entities[:4]:
            if cur + 16 > height:
                break
            color = self._entity_color(eid)
            pygame.draw.circle(surf, (*color, 230), (int(x + 3), int(cur + 6)), 3)
            name = self._text('f_nano', self._entity_label(eid, 16).upper(),
                              COLOR_TEXT_SECONDARY, spacing=1)
            surf.blit(name, (x + 12, cur))
            value = self._text('f_nano', self._entity_state_text(eid, 16).upper(),
                               color, spacing=1)
            surf.blit(value, (x + w - value.get_width(), cur))
            cur += 15
        return cur

    def _draw_lighting(self, surf, x, y, w, accent, entities, height):
        from effects_kit import draw_bar_meter
        if not entities:
            return y
        on = [e for e in entities if self.data.get(e, {}).get('state') == 'on']
        lbl = self._text('f_nano', "ILLUMINATION  POWER", accent, spacing=2)
        surf.blit(lbl, (x, y))
        count = self._text('f_nano', f"{len(on)}/{len(entities)} ACTIVE",
                           COLOR_TEXT_DIM, spacing=1)
        surf.blit(count, (x + w - count.get_width(), y))
        cur = y + lbl.get_height() + 4

        frac = len(on) / max(1, len(entities))
        draw_bar_meter(surf, x, cur, w, 5, frac, COLOR_ACCENT_AMBER,
                       segments=max(8, len(entities)))
        cur += 12

        for eid in entities[:5]:
            if cur + 20 > height:
                break
            info = self.data.get(eid, {})
            state_val = info.get('state')
            is_on = state_val in ('on', 'locked')
            color = self._entity_color(eid)
            _draw_toggle(surf, x, cur + 2, is_on, color, w=24, h=12)
            name = self._text('f_nano', self._entity_label(eid, 18).upper(),
                              COLOR_TEXT_SECONDARY if is_on else COLOR_TEXT_DIM,
                              spacing=1)
            surf.blit(name, (x + 30, cur + 3))
            brightness = (info.get('attributes') or {}).get('brightness')
            if is_on and isinstance(brightness, (int, float)):
                pct = self._text('f_nano', f"{round(brightness / 255 * 100)}%",
                                 COLOR_ACCENT_AMBER, spacing=1)
                surf.blit(pct, (x + w - pct.get_width(), cur + 3))
            cur += 18
        return cur

    # ------------------------------------------------------------------
    # Dashboard overlay (center zone, on demand)
    # ------------------------------------------------------------------

    def draw_dashboard(self, screen):
        """Draw the full dashboard overlay in the center clear zone.

        Called by the main draw loop in the active state. Fades in/out via
        _dash_alpha; draws nothing once fully faded.
        """
        try:
            if self._dash_alpha <= 0.01:
                return
            self._ensure_fonts()

            sw, sh = screen.get_width(), screen.get_height()
            zone_x = int(sw * 0.24)
            zone_w = int(sw * 0.52)
            zone_y = int(sh * 0.16)
            zone_h = int(sh * 0.62)

            overlay = pygame.Surface((zone_w, zone_h), pygame.SRCALPHA)

            # Title
            title = self.body_font.render("HOME DASHBOARD", True, COLOR_TITLE_BLUE)
            overlay.blit(title, ((zone_w - title.get_width()) // 2, 0))
            pygame.draw.line(
                overlay, (40, 40, 40),
                (zone_w // 6, title.get_height() + 8),
                (zone_w * 5 // 6, title.get_height() + 8),
            )
            top = title.get_height() + 20

            # Group entities into sections
            sections = []
            used = set()
            for label, domains in DOMAIN_SECTIONS:
                eids = [e for e in self.entities if _domain(e) in domains]
                if eids:
                    sections.append((label, eids))
                    used.update(eids)
            leftover = [e for e in self.entities if e not in used]
            if leftover:
                sections.append(("Other", leftover))

            # Flow sections down two columns
            col_w = zone_w // 2
            line_h = 30
            header_h = 36
            col_x = [10, col_w + 10]
            col_y = [top, top]
            col = 0

            def _next_col():
                return 0 if col_y[0] <= col_y[1] else 1

            for label, eids in sections:
                col = _next_col()
                if col_y[col] + header_h + line_h > zone_h - 30:
                    continue  # zone full; remaining sections dropped
                header = self.small_font.render(label.upper(), True, COLOR_TEXT_DIM)
                overlay.blit(header, (col_x[col], col_y[col] + 8))
                col_y[col] += header_h

                for eid in eids:
                    if col_y[col] + line_h > zone_h - 30:
                        break
                    state_val = self.data.get(eid, {}).get('state', '?')
                    color = self._entity_color(eid)
                    pygame.draw.circle(
                        overlay, color, (col_x[col] + 5, col_y[col] + 11), 4
                    )
                    name_surf = self.body_font.render(
                        self._entity_label(eid, max_len=18), True, COLOR_TEXT_SECONDARY
                    )
                    state_surf = self.body_font.render(
                        self._entity_state_text(eid), True, color
                    )
                    overlay.blit(name_surf, (col_x[col] + 16, col_y[col]))
                    overlay.blit(
                        state_surf,
                        (col_x[col] + col_w - state_surf.get_width() - 24, col_y[col])
                    )
                    col_y[col] += line_h

            # Footer: freshness + close hint + auto-close countdown
            age = (datetime.now() - self.last_update).total_seconds()
            remaining = max(0, int(self._dashboard_until - time.monotonic()))
            footer_text = (
                f"updated {int(age)}s ago  -  closes in {remaining}s  -  "
                f"say 'close dashboard' or press H"
            )
            footer = self.small_font.render(footer_text, True, COLOR_TEXT_DIM)
            overlay.blit(footer, ((zone_w - footer.get_width()) // 2, zone_h - 20))

            overlay.set_alpha(int(self._dash_alpha * TRANSPARENCY))
            screen.blit(overlay, (zone_x, zone_y))
        except Exception as e:
            logger.error(f"Error drawing HA dashboard: {e}")

    def cleanup(self):
        pass
