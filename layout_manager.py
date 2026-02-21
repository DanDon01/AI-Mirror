"""Zone-based layout manager for AI-Mirror.

Positions modules in edge-hugging zones around a clear center mirror area.
Top bar: scrolling clock + status. Bottom bar: scrolling stock ticker.
Left/right columns: stacked info modules. Center: clear for reflection.
"""

import logging
from config import CONFIG, LAYOUT_V2, CURRENT_MONITOR

logger = logging.getLogger("Layout")


class LayoutManager:
    def __init__(self, screen_width, screen_height):
        # Always trust the passed-in dimensions (actual display size)
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.layout = LAYOUT_V2
        self.module_positions = {}
        self.calculate_positions()
        logger.info(
            f"Layout initialized: {self.screen_width}x{self.screen_height}, "
            f"{len(self.module_positions)} positions calculated"
        )

    def calculate_positions(self):
        """Calculate zone-based module positions for mirror layout."""
        w = self.screen_width
        h = self.screen_height
        zones = self.layout['zones']
        gap = self.layout.get('module_gap', 15)
        edge_pad = self.layout.get('edge_padding', 15)

        # Zone dimensions
        top_h = zones['top_bar']['height']
        bottom_h = zones['bottom_bar']['height']
        # Use percentage of actual screen width, capped by monitor config max
        left_pct = int(w * zones['left_column']['width_pct'])
        right_pct = int(w * zones['right_column']['width_pct'])
        left_max = CURRENT_MONITOR.get('left_col_width', left_pct)
        right_max = CURRENT_MONITOR.get('right_col_width', right_pct)
        left_w = min(left_pct, left_max)
        right_w = min(right_pct, right_max)

        # Column vertical bounds (between top bar and bottom bar)
        col_top = top_h + gap
        col_bottom = h - bottom_h - gap

        # Top bar: full width
        self.module_positions['clock'] = {
            'x': 0, 'y': 0,
            'width': w, 'height': top_h,
        }

        # Bottom bar: full width, anchored to bottom
        self.module_positions['stocks'] = {
            'x': 0, 'y': h - bottom_h,
            'width': w, 'height': bottom_h,
        }

        # Left column: stacked modules
        left_modules = self.layout.get('left_modules', [])
        left_positions = self._stack_column(
            left_modules, edge_pad, left_w, col_top, col_bottom, gap
        )
        self.module_positions.update(left_positions)

        # Right column: stacked modules
        right_modules = self.layout.get('right_modules', [])
        right_x = w - right_w - edge_pad
        right_positions = self._stack_column(
            right_modules, right_x, right_w, col_top, col_bottom, gap
        )
        self.module_positions.update(right_positions)

        # Center overlay modules (AI/voice): centered on screen
        center_x = left_w + edge_pad + gap
        center_w = w - left_w - right_w - (edge_pad + gap) * 2
        center_y = h // 3
        for name in self.layout.get('center_overlay_modules', []):
            self.module_positions[name] = {
                'x': center_x, 'y': center_y,
                'width': center_w, 'height': 200,
            }

        # Fullscreen overlay (retro characters, screensaver)
        for name in self.layout.get('fullscreen_overlay_modules', []):
            self.module_positions[name] = {
                'x': 0, 'y': 0,
                'width': w, 'height': h,
            }

        for name, pos in self.module_positions.items():
            logger.info(
                f"  {name}: ({pos['x']},{pos['y']}) "
                f"{pos['width']}x{pos['height']}"
            )

    def _stack_column(self, module_names, x, width, top_y, bottom_y, gap):
        """Stack modules vertically within a column zone.

        Distributes available vertical space equally among modules.
        """
        positions = {}
        count = len(module_names)
        if count == 0:
            return positions

        available = bottom_y - top_y
        module_h = (available - (count - 1) * gap) // count
        current_y = top_y

        for name in module_names:
            positions[name] = {
                'x': x, 'y': current_y,
                'width': width, 'height': module_h,
            }
            current_y += module_h + gap

        return positions

    def get_module_position(self, module_name):
        """Get position for a module, with fallback defaults."""
        if module_name in self.module_positions:
            return self.module_positions[module_name]

        # Fallback: place unknown modules in top-left
        logger.warning(f"No position for module: {module_name}")
        return {'x': 10, 'y': 10, 'width': 300, 'height': 200}

    def get_zone(self, zone_name):
        """Get the bounds of a layout zone."""
        zones = self.layout.get('zones', {})
        return zones.get(zone_name, {})
