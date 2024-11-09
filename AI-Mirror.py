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
from stocks_module import StocksModule  # Add this import at the top
from clock_module import ClockModule  # Add this import
from retrocharacters_module import RetroCharactersModule  # Add this import
from AI_Module import AIInteractionModule  # Add this import at the top

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide" # Hide ALSA errors

# Import other modules as needed again

class MagicMirror:
    def __init__(self):
        pygame.init()
        self.setup_logging()
        logging.info("Initializing MagicMirror")
        self.screen = pygame.display.set_mode(CONFIG['screen']['size'], pygame.FULLSCREEN)
        self.clock = pygame.time.Clock()
        self.modules = self.initialize_modules()
        self.frame_rate = CONFIG.get('frame_rate', 30)
        self.running = True
        self.state = "active"  # Can be "active", "sleep", or "screensaver"
        self.font = pygame.font.Font(None, 48)  # Larger font for the clock
        logging.info(f"Initialized modules: {list(self.modules.keys())}")

    def setup_logging(self):
        handler = RotatingFileHandler('magic_mirror.log', maxBytes=1000000, backupCount=3)
        logging.basicConfig(level=logging.INFO, handlers=[handler],
                            format='%(asctime)s - %(levelname)s - %(message)s')
        logging.info("Magic Mirror started")

    def initialize_modules(self):
        modules = {}
        for module_name, module_config in CONFIG.items():
            if isinstance(module_config, dict) and 'class' in module_config:
                try:
                    module_class = globals()[module_config['class']]
                    modules[module_name] = module_class(**module_config['params'])
                    logging.info(f"Initialized {module_name} module")
                except Exception as e:
                    logging.error(f"Error initializing {module_name} module: {str(e)}")
                    logging.error(traceback.format_exc())
        
        return modules  # Remove the manual ClockModule creation

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                    pygame.quit()
                    sys.exit()
                elif event.key == pygame.K_s:
                    self.toggle_mode()
                elif event.key == pygame.K_SPACE:
                    if 'ai_interaction' in self.modules:
                        self.modules['ai_interaction'].handle_event(event)
            # Add more event handling here (e.g., for voice commands or gestures)

    def toggle_mode(self):
        if self.state == "active":
            self.state = "screensaver"
        elif self.state == "screensaver":
            self.state = "sleep"
        else:
            self.state = "active"
        logging.info(f"Mirror state changed to: {self.state}")

    def update_modules(self):
        for module_name, module in self.modules.items():
            try:
                if hasattr(module, 'update'):
                    if self.state == "screensaver" and module_name != 'retro_characters':
                        continue  # Skip updating other modules in screensaver mode
                    module.update()
            except Exception as e:
                logging.error(f"Error updating {module_name}: {e}")

    def draw_modules(self):
        try:
            self.screen.fill((0, 0, 0))  # Clear screen with black
            
            # Always draw RetroCharactersModule
            if 'retro_characters' in self.modules:
                self.modules['retro_characters'].draw(self.screen)

            if self.state == "active":
                for module_name, module in self.modules.items():
                    if module_name != 'retro_characters':  # Skip retro_characters as we've already drawn it
                        try:
                            if module_name in CONFIG['positions']:
                                module.draw(self.screen, CONFIG['positions'][module_name])
                            else:
                                logging.warning(f"No position defined for {module_name} in CONFIG")
                        except Exception as e:
                            logging.error(f"Error drawing {module_name}: {e}")
                            logging.error(traceback.format_exc())
                            error_font = pygame.font.Font(None, 24)
                            error_text = error_font.render(f"Error in {module_name}", True, (255, 0, 0))
                            self.screen.blit(error_text, (10, 10))  # Fallback position
            elif self.state == "sleep":
                # Draw sleep mode screen (e.g., just the time)
                self.modules['clock'].draw(self.screen, (0, self.screen.get_height() // 2 - 30))
            # No need for an "elif self.state == "screensaver":" block, as we're always drawing RetroCharactersModule
            
            pygame.display.flip()
            logging.debug("Updated display")
        except Exception as e:
            logging.error(f"Error in draw_modules: {e}")
            logging.error(traceback.format_exc())

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