import pygame
import sys
import logging
from datetime import datetime
from config import CONFIG
from modules import FitbitModule, StocksModule, WeatherModule, NewsModule, CalendarModule

class MagicMirror:
    def __init__(self):
        pygame.init()
        self.setup_logging()
        self.screen = pygame.display.set_mode((800, 480), pygame.FULLSCREEN)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.modules = self.initialize_modules()
        self.last_update = {module: datetime.now() for module in self.modules}
        self.update_intervals = {
            "fitbit": 300,  # 5 minutes
            "stocks": 300,  # 5 minutes
            "weather": 1800,  # 30 minutes
            "news": 3600,  # 1 hour
            "calendar": 3600  # 1 hour
        }

    def setup_logging(self):
        logging.basicConfig(filename='magic_mirror.log', level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(message)s')

    def initialize_modules(self):
        try:
            return {
                "fitbit": FitbitModule(**CONFIG['fitbit']),
                "stocks": StocksModule(**CONFIG['stocks']),
                "weather": WeatherModule(**CONFIG['weather']),
                "news": NewsModule(**CONFIG['news']),
                "calendar": CalendarModule(**CONFIG['calendar'])
            }
        except Exception as e:
            logging.error(f"Error initializing modules: {e}")
            pygame.quit()
            sys.exit(1)

    def update(self):
        current_time = datetime.now()
        for module_name, module in self.modules.items():
            if (current_time - self.last_update[module_name]).total_seconds() > self.update_intervals[module_name]:
                try:
                    module.update()
                    self.last_update[module_name] = current_time
                except Exception as e:
                    logging.error(f"Error updating {module_name}: {e}")

    def draw(self):
        self.screen.fill((0, 0, 0))  # Black background
        try:
            for module_name, module in self.modules.items():
                module.draw(self.screen, CONFIG['positions'][module_name])
            self.draw_time()
        except Exception as e:
            logging.error(f"Error drawing modules: {e}")
        pygame.display.flip()

    def draw_time(self):
        current_time = datetime.now().strftime("%H:%M:%S")
        time_surface = self.font.render(current_time, True, (255, 255, 255))
        self.screen.blit(time_surface, (10, 10))

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
        return True

    def run(self):
        try:
            while self.handle_events():
                self.update()
                self.draw()
                self.clock.tick(30)  # Limit to 30 FPS to save power
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {e}")
        finally:
            logging.info("Shutting down Magic Mirror")
            pygame.quit()
            sys.exit()

if __name__ == "__main__":
    mirror = MagicMirror()
    mirror.run()
