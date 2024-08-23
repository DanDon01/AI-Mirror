import pygame
from datetime import datetime
import pytz

class ClockModule:
    def __init__(self, font_file=None, font_size=60, color=(255, 255, 255), time_format='%H:%M:%S', date_format='%A, %B %d, %Y', timezone='local', align='vertical'):
        self.font = pygame.font.Font(font_file, font_size) if font_file else pygame.font.SysFont('Arial', font_size)
        self.date_font = pygame.font.Font(font_file, font_size // 2)  # Smaller font for the date
        self.color = color
        self.time_format = time_format
        self.date_format = date_format
        self.align = align
        if timezone != 'local':
            self.tz = pytz.timezone(timezone)
        else:
            self.tz = None

    def update(self):
        # No need for an update method as we'll get the current time when drawing
        pass

    def draw(self, screen, position):
        try:
            x, y = position
            current_time = datetime.now(self.tz) if self.tz else datetime.now()

            # Render time
            time_surface = self.font.render(current_time.strftime(self.time_format), True, self.color)
            time_width, time_height = time_surface.get_size()

            # Render date
            date_surface = self.date_font.render(current_time.strftime(self.date_format), True, self.color)
            date_width, date_height = date_surface.get_size()

            # Determine positioning based on alignment
            if self.align == 'vertical':
                screen.blit(time_surface, (x, y))
                screen.blit(date_surface, (x, y + time_height + 10))
            elif self.align == 'horizontal':
                total_width = time_width + date_width + 20  # 20 pixels gap between time and date
                screen.blit(time_surface, (x, y))
                screen.blit(date_surface, (x + time_width + 20, y))
            else:
                logging.warning(f"Unknown alignment '{self.align}'. Defaulting to vertical.")
                screen.blit(time_surface, (x, y))
                screen.blit(date_surface, (x, y + time_height + 10))
        except Exception as e:
            logging.error(f"Error drawing clock data: {e}")
            error_surface = self.font.render("Clock data unavailable", True, (255, 0, 0))
            screen.blit(error_surface, position)

    def cleanup(self):
        # No cleanup needed for this module
        pass
