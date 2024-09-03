import pygame
import logging
from datetime import datetime
import pytz

class ClockModule:
    def __init__(self, font_file=None, time_font_size=60, date_font_size=30, color=(255, 255, 255), time_format='%H:%M:%S', date_format='%A, %B %d, %Y', timezone='local'):
        self.time_font = pygame.font.Font(font_file, time_font_size) if font_file else pygame.font.SysFont('Arial', time_font_size)
        self.date_font = pygame.font.Font(font_file, date_font_size) if font_file else pygame.font.SysFont('Arial', date_font_size)
        self.color = color
        self.time_format = time_format
        self.date_format = date_format
        self.tz = pytz.timezone(timezone) if timezone != 'local' else None
        self.scroll_position = 0
        self.scroll_speed = 1

    def update(self):
        # Update scroll position
        self.scroll_position -= self.scroll_speed

    def draw(self, screen, position):
        try:
            x, y = position
            current_time = datetime.now(self.tz) if self.tz else datetime.now()

            # Render time
            time_surface = self.time_font.render(current_time.strftime(self.time_format), True, self.color)
            
            # Render date
            date_surface = self.date_font.render(current_time.strftime(self.date_format), True, self.color)

            # Calculate total width
            total_width = time_surface.get_width() + date_surface.get_width() + 20  # 20 pixels gap

            # Reset scroll position if it's off-screen
            if self.scroll_position < -total_width:
                self.scroll_position = screen.get_width()

            # Draw time
            screen.blit(time_surface, (self.scroll_position, y))
            
            # Draw date below time
            screen.blit(date_surface, (self.scroll_position, y + time_surface.get_height() + 5))

        except Exception as e:
            logging.error(f"Error drawing clock data: {e}")
            error_surface = self.time_font.render("Clock data unavailable", True, (255, 0, 0))
            screen.blit(error_surface, position)

    def cleanup(self):
        # No cleanup needed for this module
        pass
