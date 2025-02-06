import pygame
import logging
from datetime import datetime
import pytz
import calendar

class ClockModule:
    def __init__(self, font_file=None, time_font_size=60, date_font_size=30, color=(255, 255, 255), time_format='%H:%M:%S', date_format='%a, %b %d, %Y', timezone='local'):
        self.time_font = pygame.font.Font(font_file, time_font_size) if font_file else pygame.font.SysFont('Arial', time_font_size)
        self.date_font = pygame.font.Font(font_file, date_font_size) if font_file else pygame.font.SysFont('Arial', date_font_size)
        self.color = color
        self.time_format = time_format
        self.date_format = date_format
        self.tz = pytz.timezone(timezone) if timezone != 'local' else None
        self.scroll_position = 0
        self.scroll_speed = 2
        self.screen_width = 0  # This will be set in the draw method
        self.total_width = 0  # This will be calculated in the draw method

    def update(self):
        # Update scroll position
        self.scroll_position -= self.scroll_speed
        if self.total_width > 0 and self.scroll_position < -self.total_width:
            self.scroll_position = self.screen_width

    def draw(self, screen, layout_manager):
        try:
            pos = layout_manager.get_module_position('clock')
            if not pos:
                return

            start_pos = layout_manager.draw_module_background(screen, 'clock', 'Time & Date')
            if not start_pos:
                return

            x, y = start_pos
            current_time = datetime.now(self.tz) if self.tz else datetime.now()

            # Draw time with larger font
            time_surface = self.time_font.render(current_time.strftime(self.time_format), True, COLOR_TITLE)
            time_x = x + (pos['width'] - time_surface.get_width()) // 2
            screen.blit(time_surface, (time_x, y + 10))

            # Draw date with smaller font
            date_str = self.format_date(current_time)
            date_surface = self.date_font.render(date_str, True, COLOR_SUBTITLE)
            date_x = x + (pos['width'] - date_surface.get_width()) // 2
            screen.blit(date_surface, (time_x, y + time_surface.get_height() + 5))

        except Exception as e:
            logging.error(f"Error drawing clock: {e}")

    def format_date(self, date):
        # Custom date formatting to match "Tues, Sept 03, 2024" format
        day_abbr = calendar.day_abbr[date.weekday()][:4]  # Get first 4 letters of day name
        month_abbr = date.strftime("%b")
        if month_abbr == "Sep":
            month_abbr = "Sept"
        return f"{day_abbr}, {month_abbr} {date.strftime('%d')}, {date.strftime('%Y')}"

    def cleanup(self):
        # No cleanup needed for this module
        pass
