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

    def draw(self, screen, position):
        try:
            x, y = position
            self.screen_width = screen.get_width()  # Set the screen width
            current_time = datetime.now(self.tz) if self.tz else datetime.now()

            # Render time and date
            time_surface = self.time_font.render(current_time.strftime(self.time_format), True, self.color)
            date_str = self.format_date(current_time)
            date_surface = self.date_font.render(date_str, True, self.color)

            # Calculate total width (use the wider of the two surfaces)
            self.total_width = max(time_surface.get_width(), date_surface.get_width())

            # Reset scroll position if it's off-screen
            if self.scroll_position < -self.total_width:
                self.scroll_position = self.screen_width

            # Calculate centered positions for time and date
            time_x = self.scroll_position + (self.total_width - time_surface.get_width()) // 2
            date_x = self.scroll_position + (self.total_width - date_surface.get_width()) // 2

            # Draw time
            screen.blit(time_surface, (time_x, y))

            # Draw date underneath time
            screen.blit(date_surface, (date_x, y + time_surface.get_height() + 5))

        except Exception as e:
            logging.error(f"Error drawing clock data: {e}")
            error_surface = self.time_font.render("Clock data unavailable", True, (255, 0, 0))
            screen.blit(error_surface, position)

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
