import pygame
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from config import CONFIG
from modules import FitbitModule, StocksModule, WeatherModule, NewsModule, CalendarModule

class MagicMirror:
    def __init__(self):
        pygame.init()
        self.setup_logging()
        self.screen = pygame.display.set_mode(CONFIG['screen']['size'], pygame.FULLSCREEN)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.modules = self.initialize_modules()
        self.last_update = {module: datetime.now() for module in self.modules}
        self.update_intervals = CONFIG['update_intervals']
        self.frame_rate = CONFIG.get('frame_rate', 30)

    def setup_logging(self):
        handler = RotatingFileHandler('magic_mirror.log', maxBytes=1000000, backupCount=3)
        logging.basicConfig(level=logging.INFO, handlers=[handler],
                            format='%(asctime)s - %(levelname)s - %(message)s')
        logging.info("Magic Mirror started")

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
                    self.display_error(f"{module_name} update failed")

    def draw(self):
        self.screen.fill((0, 0, 0))  # Black background
        try:
            for module_name, module in self.modules.items():
                module.draw(self.screen, CONFIG['positions'][module_name])
            self.draw_time()
        except Exception as e:
            logging.error(f"Error drawing modules: {e}")
            self.display_error("Error rendering display")
        pygame.display.flip()

    def draw_time(self):
        current_time = datetime.now().strftime("%H:%M:%S")
        time_surface = self.font.render(current_time, True, (255, 255, 255))
        self.screen.blit(time_surface, CONFIG['positions'].get('time', (10, 10)))

    def display_error(self, message):
        error_surface = self.font.render(f"ERROR: {message}", True, (255, 0, 0))
        self.screen.blit(error_surface, (10, CONFIG['screen']['size'][1] - 40))

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
        return True

    def cleanup(self):
        for module_name, module in self.modules.items():
            try:
                module.cleanup()
            except Exception as e:
                logging.error(f"Error during cleanup of {module_name}: {e}")

    def run(self):
        try:
            while self.handle_events():
                self.update()
                self.draw()
                self.clock.tick(self.frame_rate)  # Configurable frame rate
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {e}")
        finally:
            logging.info("Shutting down Magic Mirror")
            self.cleanup()
            pygame.quit()
            sys.exit()

if __name__ == "__main__":
    mirror = MagicMirror()
    mirror.run()

