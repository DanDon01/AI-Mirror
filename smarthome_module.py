"""Smart Home module for AI-Mirror.

Displays Home Assistant entity states in a clean, minimal format.
Connects via HA REST API using a long-lived access token.
"""

import requests
import pygame
import logging
from datetime import datetime, timedelta
from config import (
    CONFIG, FONT_NAME, COLOR_FONT_DEFAULT, COLOR_FONT_BODY,
    COLOR_TEXT_SECONDARY, COLOR_ACCENT_GREEN, COLOR_ACCENT_RED,
    COLOR_ACCENT_AMBER, COLOR_ACCENT_BLUE, TRANSPARENCY,
)
from module_base import ModuleDrawHelper, SurfaceCache

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


def _state_color(entity_id, state):
    """Pick a display color based on entity domain and state."""
    domain = entity_id.split('.')[0] if '.' in entity_id else ''
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
                 update_interval_minutes=2, timeout=10, **kwargs):
        self.ha_url = ha_url.rstrip('/') if ha_url else ''
        self.ha_token = ha_token or ''
        self.headers = {
            "Authorization": f"Bearer {self.ha_token}",
            "content-type": "application/json",
        }
        self.entities = entities or []
        self.data = {}
        self.last_update = datetime.min
        self.update_interval = timedelta(minutes=update_interval_minutes)
        self.timeout = timeout
        self._connected = False
        self._last_error = None
        self._surface_cache = SurfaceCache()
        self._last_data_hash = None
        self._notification_callback = None

        # Fonts are lazy-initialised on first draw
        self.title_font = None
        self.body_font = None
        self.small_font = None

    def set_notification_callback(self, callback):
        """Allow main app to wire center notifications."""
        self._notification_callback = callback

    def update(self):
        current_time = datetime.now()
        if current_time - self.last_update < self.update_interval:
            return

        if not self.ha_url or not self.ha_token:
            self._last_error = "No HA URL or token configured"
            self._connected = False
            return

        if not self.entities:
            # Try auto-discovery: fetch all states and pick some useful ones
            self._auto_discover()
            if not self.entities:
                self._last_error = "No entities configured"
                return

        old_states = {eid: self.data.get(eid, {}).get('state') for eid in self.entities}

        for entity_id in self.entities:
            try:
                url = f"{self.ha_url}/api/states/{entity_id}"
                resp = requests.get(url, headers=self.headers, timeout=self.timeout)
                resp.raise_for_status()
                state = resp.json()
                self.data[entity_id] = {
                    'state': state.get('state', 'unknown'),
                    'attributes': state.get('attributes', {}),
                    'last_updated': current_time,
                    'status': 'ok',
                }
                self._connected = True
                self._last_error = None
            except requests.RequestException as e:
                logger.warning(f"HA fetch failed for {entity_id}: {e}")
                self.data[entity_id] = {
                    'state': 'unavailable',
                    'attributes': self.data.get(entity_id, {}).get('attributes', {}),
                    'last_updated': current_time,
                    'status': 'error',
                }
                self._last_error = str(e)

        self.last_update = current_time

        # Push notification if a notable state changed
        if self._notification_callback:
            for eid in self.entities:
                old = old_states.get(eid)
                new = self.data.get(eid, {}).get('state')
                if old and new and old != new:
                    domain = eid.split('.')[0] if '.' in eid else ''
                    if domain in ('lock', 'alarm_control_panel'):
                        name = self.data[eid].get('attributes', {}).get('friendly_name', eid)
                        self._notification_callback(
                            f"{name}: {new}",
                            COLOR_ACCENT_AMBER, 5000
                        )

    def _auto_discover(self):
        """Fetch all HA states and pick the first few useful entities."""
        try:
            url = f"{self.ha_url}/api/states"
            resp = requests.get(url, headers=self.headers, timeout=self.timeout)
            resp.raise_for_status()
            all_states = resp.json()

            # Pick sensors, lights, climate -- up to 8 entities
            preferred_domains = ['sensor', 'light', 'climate', 'binary_sensor', 'switch', 'lock']
            picked = []
            for domain in preferred_domains:
                for s in all_states:
                    eid = s.get('entity_id', '')
                    if eid.startswith(domain + '.') and len(picked) < 8:
                        # Skip internal/diagnostic entities
                        attrs = s.get('attributes', {})
                        if attrs.get('device_class') in ('update', 'connectivity', 'problem'):
                            continue
                        picked.append(eid)
                if len(picked) >= 8:
                    break

            if picked:
                self.entities = picked
                self._connected = True
                logger.info(f"Auto-discovered {len(picked)} HA entities: {picked}")
            else:
                logger.warning("Auto-discovery found no suitable entities")

        except Exception as e:
            logger.error(f"HA auto-discovery failed: {e}")
            self._last_error = str(e)

    def draw(self, screen, position):
        """Draw smart home entity states -- floating text, no background."""
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 300)
            else:
                x, y = position
                width, height = 300, 300

            if self.title_font is None:
                title_f, body_f, small_f = ModuleDrawHelper.get_fonts()
                self.title_font = title_f
                self.body_font = body_f
                self.small_font = small_f

            # Title
            draw_y = ModuleDrawHelper.draw_module_title(
                screen, "Smart Home", x, y, width
            )

            if not self.ha_url or not self.ha_token:
                err = self.body_font.render("HA not configured", True, COLOR_TEXT_SECONDARY)
                err.set_alpha(TRANSPARENCY)
                screen.blit(err, (x, draw_y))
                return

            if not self.data:
                if self._last_error:
                    msg = "Connection error"
                else:
                    msg = "Loading..."
                surf = self.body_font.render(msg, True, COLOR_TEXT_SECONDARY)
                surf.set_alpha(TRANSPARENCY)
                screen.blit(surf, (x, draw_y))
                return

            # Build data hash for surface caching
            data_hash = "|".join(
                f"{eid}={self.data.get(eid, {}).get('state', '?')}"
                for eid in self.entities
            )

            line_height = 24
            for i, entity_id in enumerate(self.entities):
                if draw_y > y + height - line_height:
                    break

                info = self.data.get(entity_id)
                if not info:
                    continue

                friendly_name = info['attributes'].get('friendly_name', entity_id)
                state_val = info['state']
                unit = info['attributes'].get('unit_of_measurement', '')

                # Truncate long names to fit column
                max_name_len = 16
                display_name = friendly_name[:max_name_len]
                if len(friendly_name) > max_name_len:
                    display_name = display_name.rstrip() + '..'

                # Format state text
                if unit:
                    state_text = f"{state_val}{unit}"
                else:
                    state_text = state_val.capitalize() if len(state_val) < 20 else state_val[:17] + '..'

                color = _state_color(entity_id, state_val)

                def _render_line(name=display_name, st=state_text, c=color):
                    # Name in default color, state in domain-specific color
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
                screen.blit(surf, (x, draw_y))
                draw_y += line_height

            # Connection status indicator (small text at bottom)
            if self._last_error:
                err_surf = self.small_font.render("HA: connection error", True, COLOR_ACCENT_RED)
                err_surf.set_alpha(TRANSPARENCY // 2)
                if draw_y < y + height - 16:
                    screen.blit(err_surf, (x, y + height - 16))

        except Exception as e:
            logger.error(f"Error drawing smart home module: {e}")

    def cleanup(self):
        pass
