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
        """Draw the clock with improved scrolling across the full screen"""
        try:
            x, y = position if isinstance(position, tuple) else (position['x'], position['y'])
            screen_width = screen.get_width()
            
            # Get current time and format it
            current_time = self.get_current_time()
            current_date = self.get_current_date()
            
            # Render time with larger font
            time_text = self.time_font.render(current_time, True, self.color)
            
            # For scrolling effect, calculate position based on time
            if hasattr(self, 'scroll_position'):
                # Update scroll position (slower speed)
                self.scroll_position -= 0.7  # Reduced speed (was likely 1 or 2)
                
                # Reset position when it's gone completely off left side
                if self.scroll_position < -time_text.get_width():
                    self.scroll_position = screen_width
            else:
                # Initialize scroll position at the right edge of screen
                self.scroll_position = screen_width
            
            # Draw the time text at the current scroll position
            screen.blit(time_text, (self.scroll_position, y))
            
            # If the first instance is scrolling off, draw a second instance
            if self.scroll_position < 0:
                # Calculate where to put the second instance
                second_position = self.scroll_position + time_text.get_width() + screen_width
                
                # Only draw second instance if needed to fill gap
                if second_position < screen_width:
                    screen.blit(time_text, (second_position, y))
            
            # Draw the date below the time (not scrolling)
            date_text = self.date_font.render(current_date, True, self.color)
            date_x = (screen_width - date_text.get_width()) // 2  # Center date
            screen.blit(date_text, (date_x, y + self.time_font_size + 10))
            
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
