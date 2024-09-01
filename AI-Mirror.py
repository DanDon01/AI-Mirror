import pygame
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import traceback
from config import CONFIG

# Import your modules here
from calendar_module import CalendarModule
from weather_module import WeatherModule
from fitbit_module import FitbitModule
from smarthome_module import SmartHomeModule
# Import other modules as needed again

class MagicMirror:
    def __init__(self):
        pygame.init()
        self.setup_logging()
        self.screen = pygame.display.set_mode(CONFIG['screen']['size'], pygame.FULLSCREEN)
        self.clock = pygame.time.Clock()
        self.modules = self.initialize_modules()
        self.frame_rate = CONFIG.get('frame_rate', 30)
        self.running = True
        self.state = "active"  # Can be "active" or "sleep"
        self.scroll_text = "ONLINE"
        self.scroll_x = self.screen.get_width()
        self.font = pygame.font.Font(None, 36)
        logging.info(f"Initialized modules: {list(self.modules.keys())}")

    def setup_logging(self):
        handler = RotatingFileHandler('magic_mirror.log', maxBytes=1000000, backupCount=3)
        logging.basicConfig(level=logging.DEBUG, handlers=[handler],
                            format='%(asctime)s - %(levelname)s - %(message)s')
        logging.info("Magic Mirror started")

    def initialize_modules(self):
        modules = {}
        for module_name, module_config in CONFIG.items():
            if isinstance(module_config, dict) and 'class' in module_config:
                try:
                    module_class = globals()[module_config['class']]
                    modules[module_name] = module_class(module_config['params'])
                    logging.info(f"Initialized {module_name} module")
                except Exception as e:
                    logging.error(f"Error initializing {module_name} module: {e}")
                    logging.error(traceback.format_exc())
        return modules

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_s:
                    self.toggle_sleep_mode()
            # Add more event handling here (e.g., for voice commands or gestures)

    def toggle_sleep_mode(self):
        self.state = "sleep" if self.state == "active" else "active"
        logging.info(f"Mirror state changed to: {self.state}")

    def update_modules(self):
        for module_name, module in self.modules.items():
            try:
                module.update()
            except Exception as e:
                logging.error(f"Error updating {module_name}: {e}")
        
        # Update scroll position
        self.scroll_x -= 2
        if self.scroll_x < -self.font.size(self.scroll_text)[0]:
            self.scroll_x = self.screen.get_width()

    def draw_modules(self):
        self.screen.fill((0, 0, 0))  # Clear screen with black
        if self.state == "active":
            # Draw scrolling text
            text_surface = self.font.render(self.scroll_text, True, (255, 255, 255))
            self.screen.blit(text_surface, (self.scroll_x, 10))
            
            for module_name, module in self.modules.items():
                try:
                    module.draw(self.screen, CONFIG['positions'][module_name])
                except Exception as e:
                    logging.error(f"Error drawing {module_name}: {e}")
                    error_font = pygame.font.Font(None, 24)
                    error_text = error_font.render(f"Error in {module_name}", True, (255, 0, 0))
                    self.screen.blit(error_text, CONFIG['positions'][module_name])
        else:
            # Draw sleep mode screen (e.g., just the time)
            current_time = datetime.now().strftime("%H:%M")
            font = pygame.font.Font(None, 100)
            text = font.render(current_time, True, (100, 100, 100))
            text_rect = text.get_rect(center=(self.screen.get_width() / 2, self.screen.get_height() / 2))
            self.screen.blit(text, text_rect)
        pygame.display.flip()

    def run(self):
        try:
            logging.info("Starting main loop")
            while self.running:
                self.handle_events()
                self.update_modules()
                self.draw_modules()
                self.clock.tick(self.frame_rate)
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {traceback.format_exc()}")
        finally:
            self.cleanup()
            logging.info("Shutting down Magic Mirror")
            pygame.quit()
            sys.exit()

    def cleanup(self):
        for module in self.modules.values():
            if hasattr(module, 'cleanup'):
                module.cleanup()

if __name__ == "__main__":
    mirror = MagicMirror()
    mirror.run()