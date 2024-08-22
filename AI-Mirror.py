import pygame
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import traceback
from config import CONFIG
from modules import FitbitModule, StocksModule, WeatherModule, CalendarModule, ClockModule

class MagicMirror:
    def __init__(self):
        pygame.init()
        self.setup_logging()
        self.screen = pygame.display.set_mode(CONFIG['screen']['size'], pygame.FULLSCREEN)
        self.clock = pygame.time.Clock()
        self.modules = self.initialize_modules()
        self.last_update = {module: datetime.min for module in self.modules}
        self.update_intervals = CONFIG['update_intervals']
        self.frame_rate = CONFIG.get('frame_rate', 30)
        self.error_font = pygame.font.Font(None, 24)
        self.running = True

    def setup_logging(self):
        handler = RotatingFileHandler('magic_mirror.log', maxBytes=1000000, backupCount=3)
        logging.basicConfig(level=logging.INFO, handlers=[handler],
                            format='%(asctime)s - %(levelname)s - %(message)s')
        logging.info("Magic Mirror started")

    def initialize_modules(self):
        modules = {}
        for module_name, module_config in CONFIG['modules'].items():
            try:
                module_class = globals()[module_config['class']]
                modules[module_name] = module_class(**module_config['params'])
                logging.info(f"Initialized {module_name} module")
            except Exception as e:
                logging.error(f"Error initializing {module_name} module: {e}")
                self.display_error(f"Failed to initialize {module_name}")
        return modules

    def update(self):
        current_time = datetime.now()
        for module_name, module in self.modules.items():
            if (current_time - self.last_update[module_name]).total_seconds() > self.update_intervals.get(module_name, 0):
                try:
                    module.update()
                    self.last_update[module_name] = current_time
                except Exception as e:
                    logging.error(f"Error updating {module_name}: {e}")
                    self.display_error(f"{module_name} update failed")

    def draw(self):
        self.screen.fill((0, 0, 0))  # Black background
        for module_name, module in self.modules.items():
            try:
                module.draw(self.screen, CONFIG['positions'][module_name])
            except Exception as e:
                logging.error(f"Error drawing {module_name}: {e}")
                self.display_error(f"Error rendering {module_name}")
        pygame.display.flip()

    def display_error(self, message):
        error_surface = self.error_font.render(f"ERROR: {message}", True, (255, 0, 0))
        self.screen.blit(error_surface, (10, CONFIG['screen']['size'][1] - 30))

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_r:
                    self.reload_modules()

    def cleanup(self):
        for module_name, module in self.modules.items():
            try:
                module.cleanup()
            except Exception as e:
                logging.error(f"Error during cleanup of {module_name}: {e}")

    def reload_modules(self):
        logging.info("Reloading modules")
        self.cleanup()
        self.modules = self.initialize_modules()
        self.last_update = {module: datetime.min for module in self.modules}

    def run(self):
        try:
            while self.running:
                self.handle_events()
                self.update()
                self.draw()
                self.clock.tick(self.frame_rate)
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {traceback.format_exc()}")
            self.display_error("Critical error occurred")
            pygame.time.wait(5000)  # Display error for 5 seconds
        finally:
            logging.info("Shutting down Magic Mirror")
            self.cleanup()
            pygame.quit()
            sys.exit()

if __name__ == "__main__":
    mirror = MagicMirror()
    mirror.run()

