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
from module_manager import ModuleManager  # Add this import

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide" # Hide ALSA errors

# Import other modules as needed again

class SpeechLogger:
    def __init__(self):
        # Set up speech logger
        self.speech_logger = logging.getLogger('speech_logger')
        self.speech_logger.setLevel(logging.INFO)
        
        # Create rotating file handler for speech log
        speech_handler = RotatingFileHandler(
            'speech_history.log',
            maxBytes=1000000,
            backupCount=5
        )
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        speech_handler.setFormatter(formatter)
        
        # Prevent duplicate logs
        self.speech_logger.propagate = False
        
        # Add handler to logger
        self.speech_logger.addHandler(speech_handler)
    
    def log_user_speech(self, text, was_command=False):
        """Log what the user said"""
        if was_command:
            self.speech_logger.info(f"USER COMMAND: {text}")
        else:
            self.speech_logger.info(f"USER: {text}")
    
    def log_ai_response(self, text):
        """Log what the AI responded"""
        self.speech_logger.info(f"AI: {text}")

class MagicMirror:
    def __init__(self):
        pygame.init()
        self.setup_logging()
        self.speech_logger = SpeechLogger()  # Add speech logger
        logging.info("Initializing MagicMirror")
        self.screen = pygame.display.set_mode(CONFIG['screen']['size'], pygame.FULLSCREEN)
        self.clock = pygame.time.Clock()
        self.modules = self.initialize_modules()
        self.frame_rate = CONFIG.get('frame_rate', 30)
        self.running = True
        self.state = "active"
        self.font = pygame.font.Font(None, 48)
        self.module_manager = ModuleManager()
        logging.info(f"Initialized modules: {list(self.modules.keys())}")

    def setup_logging(self):
        # Set up system logger
        handler = RotatingFileHandler('magic_mirror.log', maxBytes=1000000, backupCount=3)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)
        
        # Prevent duplicate logs
        for existing_handler in root_logger.handlers[:]:
            if isinstance(existing_handler, logging.StreamHandler):
                root_logger.removeHandler(existing_handler)

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
        # Check for AI commands first
        if 'ai_interaction' in self.modules:
            while not self.modules['ai_interaction'].response_queue.empty():
                msg_type, content = self.modules['ai_interaction'].response_queue.get()
                if msg_type == 'command':
                    self.module_manager.handle_command(content['command'])
                    self.speech_logger.log_user_speech(content['text'], was_command=True)
                elif msg_type == 'speech':
                    self.speech_logger.log_user_speech(content['user_text'])
                    if content['ai_response']:
                        self.speech_logger.log_ai_response(content['ai_response'])
        
        # Rest of update_modules remains the same
        for module_name, module in self.modules.items():
            if self.module_manager.is_module_visible(module_name):
                try:
                    if hasattr(module, 'update'):
                        if self.state == "screensaver" and module_name != 'retro_characters':
                            continue
                        module.update()
                except Exception as e:
                    logging.error(f"Error updating {module_name}: {e}")

    def draw_modules(self):
        try:
            self.screen.fill((0, 0, 0))  # Black background
            
            # Add debug logging
            logging.info("Drawing modules:")
            logging.info(f"Available modules: {list(self.modules.keys())}")
            logging.info(f"Module visibility states: {self.module_manager.module_visibility}")
            
            # Draw only visible modules
            for module_name, module in self.modules.items():
                logging.info(f"Attempting to draw {module_name}")
                if self.module_manager.is_module_visible(module_name):
                    if module_name in CONFIG['positions']:
                        position = CONFIG['positions'][module_name]
                        logging.info(f"Drawing {module_name} at position {position}")
                        module.draw(self.screen, position)
                    else:
                        logging.warning(f"No position defined for {module_name} in CONFIG")
            
            pygame.display.flip()
        except Exception as e:
            logging.error(f"Error in draw_modules: {e}")
            logging.error(traceback.format_exc())  # Add full traceback

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