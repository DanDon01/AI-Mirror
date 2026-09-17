"""Phone module for AI-Mirror.

Shows what matters from the phone as you pass the mirror:
  - Leave countdown: next timed Google Calendar event minus a travel
    buffer -> "Leave in 38 min" (amber "Leave now" once due). Reads the
    events already fetched by the calendar module - no extra API calls.
  - Battery: iPhone battery level/state from the Home Assistant
    Companion app sensors, auto-discovered from /api/states (or pinned
    via battery_entity in config).

Deliberately minimal (user request): no email, no messages, no
notification content. Extend here later.
"""

import logging
from datetime import datetime, timedelta, timezone

import pygame

from config import (
    CONFIG, TRANSPARENCY, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_DIM, COLOR_ACCENT_GREEN, COLOR_ACCENT_RED,
    COLOR_ACCENT_AMBER, load_font,
)
from module_base import ModuleDrawHelper, SurfaceCache, InstrumentPanel
from api_tracker import api_tracker
from background_fetcher import BackgroundFetcher

logger = logging.getLogger("Phone")

import requests


class PhoneModule(InstrumentPanel):
    def __init__(self, ha_url='', ha_token='', battery_entity='',
                 travel_minutes=25, lead_window_minutes=180,
                 update_interval_minutes=5, **kwargs):
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
        self.battery_entity = battery_entity
        self.travel_minutes = travel_minutes
        self.lead_window = timedelta(minutes=lead_window_minutes)
        self.update_interval = timedelta(minutes=update_interval_minutes)

        self.battery_level = None      # int percent
        self.battery_state = None      # "Charging" / "Not Charging" / "Full"
        self._battery_state_entity = ''
        self.last_update = datetime.min
        self._fetcher = BackgroundFetcher("phone")

        # Calendar module reference, wired by AI-Mirror
        self._calendar = None
        self._home_source = None
        self._home_source_updated = datetime.min
        self._leave = None             # (summary, start_dt, leave_dt)
        self._leave_checked_minute = None

        self._surface_cache = SurfaceCache()
        self.title_font = None
        self.body_font = None
        self.small_font = None

    def set_calendar_source(self, calendar_module):
        """Wire the calendar module whose events drive the leave countdown."""
        self._calendar = calendar_module

    def set_home_source(self, smarthome_module):
        """Use Smart Home's one shared `/api/states` snapshot when available."""
        self._home_source = smarthome_module
        logger.info("Phone battery will reuse the Smart Home HA snapshot")

    # ------------------------------------------------------------------
    # Battery via Home Assistant (background fetch)
    # ------------------------------------------------------------------

    def _fetch_states_blocking(self):
        url = f"{self.ha_url}/api/states"
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            resp.raise_for_status()
        except Exception:
            api_tracker.failure("phone", "home-assistant")
            raise
        api_tracker.record("phone", "home-assistant")
        return resp.json()

    def _discover_battery(self, states):
        """Find the iPhone battery sensors from the Companion app."""
        if self.battery_entity:
            return
        candidates = []
        for s in states:
            eid = s.get('entity_id', '')
            attrs = s.get('attributes', {})
            if not eid.startswith('sensor.'):
                continue
            if attrs.get('device_class') == 'battery' or eid.endswith('_battery_level'):
                name = (attrs.get('friendly_name') or eid).lower()
                score = 0
                if 'iphone' in eid or 'iphone' in name:
                    score += 2
                if 'phone' in eid or 'phone' in name:
                    score += 1
                candidates.append((score, eid))
        if candidates:
            candidates.sort(reverse=True)
            self.battery_entity = candidates[0][1]
            logger.info(f"Discovered phone battery entity: {self.battery_entity}")

    def _apply_states(self, states):
        self._discover_battery(states)
        if not self.battery_entity:
            return
        if not self._battery_state_entity:
            guess = self.battery_entity.replace('_battery_level', '_battery_state')
            if guess != self.battery_entity and any(
                    s.get('entity_id') == guess for s in states):
                self._battery_state_entity = guess

        by_id = {s.get('entity_id'): s for s in states}
        level = by_id.get(self.battery_entity, {}).get('state')
        try:
            self.battery_level = int(float(level))
        except (TypeError, ValueError):
            self.battery_level = None
        if self._battery_state_entity:
            self.battery_state = by_id.get(
                self._battery_state_entity, {}).get('state')

    # ------------------------------------------------------------------
    # Leave countdown from calendar events
    # ------------------------------------------------------------------

    def _compute_leave(self):
        """Next timed event within the lead window -> leave time."""
        events = getattr(self._calendar, 'events', None) if self._calendar else None
        if not events:
            return None
        now = datetime.now(timezone.utc).astimezone()
        for event in events:
            start = event.get('start', {})
            iso = start.get('dateTime')
            if not iso:
                continue  # all-day events have no leave time
            try:
                start_dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.astimezone()
            except ValueError:
                continue
            if start_dt <= now:
                continue
            leave_dt = start_dt - timedelta(minutes=self.travel_minutes)
            if leave_dt - now > self.lead_window:
                return None  # next event is too far out to count down
            summary = event.get('summary', 'event')
            return (summary, start_dt, leave_dt)
        return None

    # ------------------------------------------------------------------
    # Module interface
    # ------------------------------------------------------------------

    def update(self):
        # Leave countdown: recompute once a minute (event list is small)
        minute = datetime.now().strftime('%H:%M')
        if minute != self._leave_checked_minute:
            self._leave_checked_minute = minute
            try:
                self._leave = self._compute_leave()
            except Exception as e:
                logger.debug(f"Leave computation failed: {e}")
                self._leave = None

        # Smart Home already fetches the complete HA state list. Reuse it for
        # phone battery data rather than doubling requests to `/api/states`.
        if self._home_source is not None:
            snapshot = self._home_source.states_snapshot()
            if snapshot is not None:
                states, updated_at = snapshot
                if updated_at != self._home_source_updated:
                    self._apply_states(states)
                    self._home_source_updated = updated_at
                    self.last_update = updated_at
            return

        if not self.ha_url or not self.ha_token:
            return

        result = self._fetcher.take_result()
        if result is not None:
            ok, value = result
            if ok:
                self._apply_states(value)
            else:
                logger.warning(f"Phone HA fetch failed: {value}")
            self.last_update = datetime.now()

        if datetime.now() - self.last_update < self.update_interval:
            return
        if not api_tracker.allow("phone", "home-assistant"):
            # Blocked: wait a full interval before retrying allow()
            self.last_update = datetime.now()
            return
        self._fetcher.submit(self._fetch_states_blocking)

    def _battery_color(self):
        if self.battery_level is None:
            return COLOR_TEXT_SECONDARY
        if self.battery_level <= 20:
            return COLOR_ACCENT_RED
        if self.battery_level <= 50:
            return COLOR_ACCENT_AMBER
        return COLOR_ACCENT_GREEN

    @staticmethod
    def _battery_glyph(surf, x, y, w, h, level, color, charging):
        """A real battery cell: shell, terminal, segmented charge."""
        pygame.draw.rect(surf, (*color, 190), (int(x), int(y), int(w), int(h)), 1)
        pygame.draw.rect(surf, (*color, 190),
                         (int(x + w), int(y + h * 0.3), 2, int(h * 0.4)))
        inner_w = (w - 4) * max(0.0, min(1.0, level / 100.0))
        if inner_w > 0:
            pygame.draw.rect(surf, (*color, 235),
                             (int(x + 2), int(y + 2), int(inner_w), int(h - 4)))
        if charging:
            cx, cy = x + w / 2, y + h / 2
            pygame.draw.polygon(surf, (255, 255, 255, 240), [
                (cx + 1, cy - 6), (cx - 4, cy + 1), (cx, cy + 1),
                (cx - 1, cy + 6), (cx + 4, cy - 1), (cx, cy - 1)])

    def draw(self, screen, position):
        """UPLINK: personal device state and departure timing."""
        self.draw_instrument(screen, position, default=(300, 200))

    def _render_panel(self, surf, width, height, position=None):
        from effects_kit import draw_bar_meter
        import theme
        accent = theme.module_accent('phone')
        pad = 6
        ix, iw = pad, width - pad * 2

        now = datetime.now(timezone.utc).astimezone()
        mins_left = None
        if self._leave:
            mins_left = int((self._leave[2] - now).total_seconds() // 60)

        charging = (self.battery_state or '').lower() in ('charging', 'full')
        cur = self._panel_header(
            surf, ix, 0, iw, "Uplink", accent, align='right',
            subtitle="PERSONAL DEVICE",
            right_text="CHARGING" if charging else None,
            right_color=COLOR_ACCENT_GREEN)

        # Departure timing is the actionable value, so it leads
        if self._leave:
            summary, start_dt, _leave_dt = self._leave
            if mins_left is not None and mins_left > 0:
                hero_text, hero_color = str(mins_left), COLOR_TEXT_PRIMARY
                unit = "MIN TO LEAVE"
            else:
                hero_text, hero_color = "GO", COLOR_ACCENT_AMBER
                unit = "LEAVE NOW"
            hero = self._text('f_hero', hero_text, hero_color)
            surf.blit(hero, (ix + iw - hero.get_width(), cur))
            ul = self._text('f_nano', unit, COLOR_TEXT_DIM, spacing=2)
            surf.blit(ul, (ix + iw - ul.get_width(), cur + hero.get_height() - 2))
            sub = self._text('f_nano',
                             f"{str(summary)[:20].upper()}  {start_dt.astimezone().strftime('%H:%M')}",
                             COLOR_TEXT_SECONDARY, spacing=1)
            surf.blit(sub, (ix + iw - sub.get_width(),
                            cur + hero.get_height() + ul.get_height()))
            cur += hero.get_height() + ul.get_height() + sub.get_height() + 8

        if self.battery_level is not None and cur + 22 < height:
            color = self._battery_color()
            lbl = self._text('f_nano', "CELL", COLOR_TEXT_SECONDARY, spacing=2)
            surf.blit(lbl, (ix, cur))
            pct = self._text('f_small', f"{self.battery_level}%", color)
            surf.blit(pct, (ix + iw - pct.get_width(), cur - 3))
            self._battery_glyph(surf, ix + 30, cur - 1, 30, 13,
                                self.battery_level, color, charging)
            draw_bar_meter(surf, ix, cur + 15, iw, 4, self.battery_level / 100.0,
                           color, segments=max(8, int(iw / 12)))


    def cleanup(self):
        pass
