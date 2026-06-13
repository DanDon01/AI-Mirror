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
import requests
import pygame
import logging
import time
from datetime import datetime, timedelta
from config import (
    CONFIG, FONT_NAME, COLOR_FONT_DEFAULT, COLOR_FONT_BODY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM, COLOR_TITLE_BLUE,
    COLOR_ACCENT_GREEN, COLOR_ACCENT_RED, COLOR_ACCENT_AMBER,
    COLOR_ACCENT_BLUE, TRANSPARENCY,
)
from module_base import ModuleDrawHelper, SurfaceCache
from api_tracker import api_tracker
from background_fetcher import BackgroundFetcher

logger = logging.getLogger("SmartHome")

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
}

# Dashboard section grouping by entity domain
DOMAIN_SECTIONS = [
    ('Lights', ('light',)),
    ('Climate', ('climate',)),
    ('Security', ('lock', 'alarm_control_panel')),
    ('Switches', ('switch',)),
    ('Sensors', ('sensor', 'binary_sensor')),
]


def _domain(entity_id):
    return entity_id.split('.')[0] if '.' in entity_id else ''


def _state_color(entity_id, state):
    """Pick a display color based on entity domain and state."""
    domain = _domain(entity_id)
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


class SmartHomeModule:
    def __init__(self, ha_url, ha_token, entities=None,
                 update_interval_minutes=2, timeout=10,
                 max_entities=20, mini_entities=8,
                 dashboard_timeout=60, **kwargs):
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
        self.max_entities = max_entities
        self.mini_entities = mini_entities
        self.data = {}
        self.last_update = datetime.min
        self.update_interval = timedelta(minutes=update_interval_minutes)
        self.dashboard_update_interval = timedelta(seconds=30)
        self.timeout = timeout
        self._connected = False
        self._last_error = None
        self._surface_cache = SurfaceCache()
        self._last_data_hash = None
        self._notification_callback = None
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

    def _pick_entities(self, all_states):
        """Auto-discover: pick the most useful entities up to max_entities."""
        preferred_domains = ['sensor', 'light', 'climate', 'binary_sensor', 'switch', 'lock']
        picked = []
        for domain in preferred_domains:
            for s in all_states:
                eid = s.get('entity_id', '')
                if eid.startswith(domain + '.') and len(picked) < self.max_entities:
                    # Skip internal/diagnostic entities
                    attrs = s.get('attributes', {})
                    if attrs.get('device_class') in ('update', 'connectivity', 'problem'):
                        continue
                    picked.append(eid)
            if len(picked) >= self.max_entities:
                break

        if picked:
            self.entities = picked
            logger.info(f"Auto-discovered {len(picked)} HA entities: {picked}")
        else:
            logger.warning("Auto-discovery found no suitable entities")

    def _apply_states(self, all_states):
        current_time = datetime.now()
        if not self.entities:
            self._pick_entities(all_states)
            if not self.entities:
                self._last_error = "No entities found"
                return

        old_states = {eid: self.data.get(eid, {}).get('state') for eid in self.entities}

        by_id = {s.get('entity_id'): s for s in all_states}
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
        if self._notification_callback:
            for eid in self.entities:
                old = old_states.get(eid)
                new = self.data.get(eid, {}).get('state')
                if old and new and old != new:
                    if _domain(eid) in ('lock', 'alarm_control_panel'):
                        name = self.data[eid].get('attributes', {}).get('friendly_name', eid)
                        self._notification_callback(
                            f"{name}: {new}",
                            COLOR_ACCENT_AMBER, 5000
                        )

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
        state_val = info.get('state', '?')
        unit = info.get('attributes', {}).get('unit_of_measurement', '')
        if unit:
            return f"{state_val}{unit}"
        return (state_val.capitalize() if len(state_val) < max_len
                else state_val[:max_len - 3] + '..')

    def _summary_text(self):
        """One-line rollup for the mini view, e.g. '3 on - 21.4C'."""
        parts = []
        on_count = sum(
            1 for eid in self.entities
            if _domain(eid) in ('light', 'switch')
            and self.data.get(eid, {}).get('state') == 'on'
        )
        if any(_domain(eid) in ('light', 'switch') for eid in self.entities):
            parts.append(f"{on_count} on")
        for eid in self.entities:
            if _domain(eid) in ('climate', 'sensor'):
                info = self.data.get(eid, {})
                unit = info.get('attributes', {}).get('unit_of_measurement', '')
                if 'C' in unit or 'F' in unit:
                    parts.append(f"{info.get('state', '?')}{unit}")
                    break
        locked = [eid for eid in self.entities if _domain(eid) == 'lock']
        if locked:
            all_locked = all(
                self.data.get(eid, {}).get('state') == 'locked' for eid in locked
            )
            parts.append("locked" if all_locked else "UNLOCKED")
        return "  -  ".join(parts)

    # ------------------------------------------------------------------
    # Mini view (left column)
    # ------------------------------------------------------------------

    def draw(self, screen, position):
        """Draw the mini smart home view -- floating text, no background."""
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 300)
            else:
                x, y = position
                width, height = 300, 300

            self._ensure_fonts()
            draw_y = ModuleDrawHelper.draw_module_title(
                screen, "Smart Home", x, y, width
            )

            if not self.ha_url or not self.ha_token:
                err = self.body_font.render("HA not configured", True, COLOR_TEXT_SECONDARY)
                err.set_alpha(TRANSPARENCY)
                screen.blit(err, (x, draw_y))
                return

            if not self.data:
                msg = "Connection error" if self._last_error else "Loading..."
                surf = self.body_font.render(msg, True, COLOR_TEXT_SECONDARY)
                surf.set_alpha(TRANSPARENCY)
                screen.blit(surf, (x, draw_y))
                return

            shown = self.entities[:self.mini_entities]
            data_hash = "|".join(
                f"{eid}={self.data.get(eid, {}).get('state', '?')}"
                for eid in self.entities
            )

            # Summary rollup line
            summary = self._summary_text()
            if summary:
                def _render_summary(s=summary):
                    surf = self.small_font.render(s, True, COLOR_FONT_BODY)
                    surf.set_alpha(TRANSPARENCY)
                    return surf
                surf = self._surface_cache.get_or_render(
                    "ha_summary", _render_summary, data_hash
                )
                screen.blit(surf, (x, draw_y))
                draw_y += 24

            line_height = 24
            for i, entity_id in enumerate(shown):
                if draw_y > y + height - line_height:
                    break
                info = self.data.get(entity_id)
                if not info:
                    continue

                state_val = info['state']
                color = _state_color(entity_id, state_val)

                # Colored state dot, then name + state text
                pygame.draw.circle(screen, color, (x + 4, draw_y + 9), 4)

                def _render_line(name=self._entity_label(entity_id),
                                 st=self._entity_state_text(entity_id),
                                 c=color):
                    name_surf = self.small_font.render(f"{name}  ", True, COLOR_TEXT_SECONDARY)
                    state_surf = self.small_font.render(st, True, c)
                    total_w = name_surf.get_width() + state_surf.get_width()
                    h = max(name_surf.get_height(), state_surf.get_height())
                    combined = pygame.Surface((total_w, h), pygame.SRCALPHA)
                    combined.blit(name_surf, (0, 0))
                    combined.blit(state_surf, (name_surf.get_width(), 0))
                    combined.set_alpha(TRANSPARENCY)
                    return combined

                surf = self._surface_cache.get_or_render(
                    f"ha_line_{i}", _render_line, data_hash
                )
                screen.blit(surf, (x + 14, draw_y))
                draw_y += line_height

            # More-entities hint when the dashboard has extra content
            if len(self.entities) > len(shown):
                hint = self.small_font.render(
                    f"+{len(self.entities) - len(shown)} more on dashboard",
                    True, COLOR_TEXT_DIM
                )
                hint.set_alpha(TRANSPARENCY // 2)
                if draw_y < y + height - 16:
                    screen.blit(hint, (x + 14, draw_y))

            if self._last_error:
                err_surf = self.small_font.render("HA: connection error", True, COLOR_ACCENT_RED)
                err_surf.set_alpha(TRANSPARENCY // 2)
                if draw_y < y + height - 16:
                    screen.blit(err_surf, (x, y + height - 16))

        except Exception as e:
            logger.error(f"Error drawing smart home module: {e}")

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
                    color = _state_color(eid, state_val)
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
