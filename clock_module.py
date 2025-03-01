import pygame
import logging
from datetime import datetime
import pytz
import calendar

class ClockModule:
    def __init__(self, font_file=None, time_font_size=60, date_font_size=30, color=(255, 255, 255), time_format='%H:%M:%S', date_format='%a, %b %d, %Y', timezone='local'):
        self.width = 300  # Default module width
        self.height = 150  # Default module height
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
        """Draw clock with error handling"""
        try:
            # Make sure position is a tuple or dict we can use
            if isinstance(position, dict) and 'x' in position and 'y' in position:
                x, y = position['x'], position['y']
            elif isinstance(position, (list, tuple)) and len(position) >= 2:
                x, y = position[0], position[1]
            else:
                # Fallback position
                x, y = 10, 10
            
            # Get current time
            current_time = datetime.now()
            date_str = current_time.strftime("%A, %B %d, %Y")
            time_str = current_time.strftime("%I:%M:%S %p")
            
            # Render time with large font
            time_font = pygame.font.SysFont('Arial', 72)
            time_surface = time_font.render(time_str, True, (200, 200, 200))
            
            # Render date with smaller font
            date_font = pygame.font.SysFont('Arial', 36)
            date_surface = date_font.render(date_str, True, (180, 180, 180))
            
            # Calculate positions for centered text
            time_x = x + (self.width - time_surface.get_width()) // 2
            date_x = x + (self.width - date_surface.get_width()) // 2
            
            # Draw to screen
            screen.blit(time_surface, (time_x, y))
            screen.blit(date_surface, (date_x, y + time_surface.get_height() + 10))
            
        except Exception as e:
            # Handle any errors gracefully
            print(f"Error drawing clock: {e}")
            error_font = pygame.font.SysFont('Arial', 24)
            error_surface = error_font.render("Clock Error", True, (255, 0, 0))
            screen.blit(error_surface, (x, y))

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
