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
from module_base import ModuleDrawHelper, SurfaceCache
from api_tracker import api_tracker
from background_fetcher import BackgroundFetcher

logger = logging.getLogger("Phone")

import requests


class PhoneModule:
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
        self._leave = None             # (summary, start_dt, leave_dt)
        self._leave_checked_minute = None

        self._surface_cache = SurfaceCache()
        self.title_font = None
        self.body_font = None
        self.small_font = None

    def set_calendar_source(self, calendar_module):
        """Wire the calendar module whose events drive the leave countdown."""
        self._calendar = calendar_module

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

    def draw(self, screen, position):
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 200)
            else:
                x, y = position
                width, height = 300, 200

            align = position.get('align', 'left') if isinstance(position, dict) else 'left'

            if self.title_font is None:
                tf, bf, sf = ModuleDrawHelper.get_fonts()
                self.title_font = tf
                self.body_font = bf
                self.small_font = sf

            draw_y = ModuleDrawHelper.draw_module_title(
                screen, "Phone", x, y, width, align=align
            )

            now = datetime.now(timezone.utc).astimezone()
            mins_left = None
            if self._leave:
                mins_left = int((self._leave[2] - now).total_seconds() // 60)

            data_hash = f"{mins_left}|{self.battery_level}|{self.battery_state}"

            # Leave countdown hero
            if self._leave:
                summary, start_dt, leave_dt = self._leave
                if mins_left is not None and mins_left > 0:
                    hero_text = f"Leave in {mins_left} min"
                    hero_color = COLOR_TEXT_PRIMARY
                else:
                    hero_text = "Leave now"
                    hero_color = COLOR_ACCENT_AMBER

                def _render_hero(t=hero_text, c=hero_color):
                    s = load_font('light', 26).render(t, True, c)
                    s.set_alpha(TRANSPARENCY)
                    return s

                hero = self._surface_cache.get_or_render(
                    "leave_hero", _render_hero, data_hash
                )
                ModuleDrawHelper.blit_aligned(screen, hero, x, draw_y, width, align)
                draw_y += hero.get_height() + 4

                sub_text = f"{summary[:24]}  {start_dt.astimezone().strftime('%H:%M')}"

                def _render_sub(t=sub_text):
                    s = self.small_font.render(t, True, COLOR_TEXT_DIM)
                    s.set_alpha(TRANSPARENCY)
                    return s

                sub = self._surface_cache.get_or_render(
                    "leave_sub", _render_sub, data_hash
                )
                ModuleDrawHelper.blit_aligned(screen, sub, x, draw_y, width, align)
                draw_y += sub.get_height() + 12

            # Battery row
            if self.battery_level is not None:
                charging = (self.battery_state or '').lower() in ('charging', 'full')
                batt_text = f"Battery {self.battery_level}%"
                if charging:
                    batt_text += "  charging"

                def _render_batt(t=batt_text, c=self._battery_color()):
                    label = self.small_font.render("Battery ", True, COLOR_TEXT_SECONDARY)
                    value = self.small_font.render(
                        t.replace("Battery ", ""), True, c
                    )
                    combined = pygame.Surface(
                        (label.get_width() + value.get_width(),
                         max(label.get_height(), value.get_height())),
                        pygame.SRCALPHA,
                    )
                    combined.blit(label, (0, 0))
                    combined.blit(value, (label.get_width(), 0))
                    combined.set_alpha(TRANSPARENCY)
                    return combined

                batt = self._surface_cache.get_or_render(
                    "battery", _render_batt, data_hash
                )
                ModuleDrawHelper.blit_aligned(screen, batt, x, draw_y, width, align)
                draw_y += batt.get_height() + 6
            elif self.ha_url and not self._leave:
                msg = self.small_font.render("Waiting for phone data...", True, COLOR_TEXT_DIM)
                msg.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(screen, msg, x, draw_y, width, align)

        except Exception as e:
            logger.error(f"Error drawing phone module: {e}")

    def cleanup(self):
        pass
