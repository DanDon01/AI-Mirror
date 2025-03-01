#  Code for the main Magic Mirror application that runs on the Raspberry Pi
#  This code is responsible for initializing the modules, handling events, updating the modules, and drawing the modules on the screen
#  It also handles toggling between active, screensaver, and sleep states, and toggling debug mode on/off
#  The main loop runs until the user closes the application

# Block JACK server completely
import os
import sys

# Set environment variables to disable problematic audio components
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"  
os.environ['ALSA_CARD'] = "3"  # Force ALSA to use card 3 (your USB device)
os.environ['PA_ALSA_PLUGHW'] = "1"  # Force PortAudio to use hw devices
os.environ['NOPORT'] = '1'  # Tell PortAudio to skip JACK
os.environ['AUDIODEV'] = 'null'  # Use null audio device if no others work
os.environ['AUDIODRIVER'] = 'alsa'  # Force ALSA as audio driver

# Completely suppress ALSA errors by loading libasound with custom error handler
try:
    # Load the ALSA library and set error handler to quiet mode
    alsa_lib = ctypes.CDLL(util.find_library('asound'))
    # Define the silent error handler
    ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int, 
                                          ctypes.c_char_p, ctypes.c_int, 
                                          ctypes.c_char_p)
    def py_error_handler(filename, line, function, err, fmt):
        pass  # Do nothing instead of printing errors
    # Pass the function pointer to C
    c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
    # Set the error handler
    alsa_lib.snd_lib_error_set_handler(c_error_handler)
except:
    pass  # If this fails, we'll try other methods

# Redirect standard error output to /dev/null for the entire program
sys.stderr = open(os.devnull, 'w')

# Now import the problematic libraries
import pygame
import pyaudio
import speech_recognition

# Restore stderr
sys.stderr = open(os.devnull, 'w')

# Import the problematic libraries
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
from stocks_module import StocksModule 
from clock_module import ClockModule  
from retrocharacters_module import RetroCharactersModule 
from ai_module_manager import AIModuleManager
from module_manager import ModuleManager 
from layout_manager import LayoutManager

import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

# After importing all audio libraries, restore stderr for normal logging
import sys
sys.stderr = sys.__stderr__

# Set up a null handler for ALSA messages
class NullHandler:
    def write(self, s):
        if not any(x in s for x in ["ALSA", "jack server"]):
            sys.__stderr__.write(s)
    def flush(self):
        sys.__stderr__.flush()

# Replace stderr with our custom handler
sys.stderr = NullHandler()

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
        self.debug_mode = CONFIG.get('debug', {}).get('enabled', False)
        self.setup_logging()
        pygame.init()
        self.speech_logger = SpeechLogger()
        logging.info("Initializing MagicMirror")
        self.screen = pygame.display.set_mode(CONFIG['screen']['size'], pygame.FULLSCREEN)
        self.clock = pygame.time.Clock()
        self.modules = self.initialize_modules()
        self.frame_rate = CONFIG.get('frame_rate', 30)
        self.running = True
        self.state = "active"
        self.font = pygame.font.Font(None, 48)
        self.module_manager = ModuleManager()
        # Initialize module visibility with all modules
        for module_name in self.modules.keys():
            self.module_manager.module_visibility[module_name] = True
        logging.info(f"Initialized modules: {list(self.modules.keys())}")
        self.layout_manager = LayoutManager(CONFIG['screen']['size'][0], CONFIG['screen']['size'][1])

    def setup_logging(self):
        """Set up logging configuration"""
        # Remove all existing handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # Create main log file handler
        file_handler = RotatingFileHandler(
            'magic_mirror.log',
            maxBytes=1000000,
            backupCount=5
        )
        
        # Create console handler
        console_handler = logging.StreamHandler()
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Get root logger and set level based on config
        root_logger = logging.getLogger()
        log_level = CONFIG.get('debug', {}).get('log_level', 'INFO')
        root_logger.setLevel(getattr(logging, log_level))
        
        # Add handlers
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        # Prevent propagation of logs to prevent duplicates
        logging.getLogger('speech_logger').propagate = False

    def debug_log(self, message):
        """Helper method for debug logging"""
        if self.debug_mode:
            logging.debug(message)

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
        
        return modules

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
                elif event.key == pygame.K_d:
                    self.toggle_debug()
                elif event.key == pygame.K_SPACE:
                    if 'ai_module' in self.modules:
                        self.modules['ai_module'].handle_event(event)
            # Add more event handling here (e.g., for voice commands or gestures)

    def toggle_mode(self):
        if self.state == "active":
            self.state = "screensaver"
        elif self.state == "screensaver":
            self.state = "sleep"
        else:
            self.state = "active"
        logging.info(f"Mirror state changed to: {self.state}")

    def draw_modules(self):
        try:
            self.screen.fill((0, 0, 0))  # Black background
            
            # Debug logging only when debug mode is enabled
            self.debug_log("Drawing modules:")
            self.debug_log(f"Available modules: {list(self.modules.keys())}")
            self.debug_log(f"Module visibility states: {self.module_manager.module_visibility}")
            
            # Draw only visible modules
            for module_name, module in self.modules.items():
                self.debug_log(f"Attempting to draw {module_name}")
                if self.module_manager.is_module_visible(module_name):
                    try:
                        position = self.layout_manager.get_module_position(module_name)
                        if position:
                            self.debug_log(f"Drawing {module_name} at position {position}")
                            module.draw(self.screen, (position['x'], position['y']))
                        else:
                            logging.warning(f"No position defined for {module_name}")
                    except Exception as e:
                        logging.error(f"Error drawing module {module_name}: {str(e)}")
            
            pygame.display.flip()
        except Exception as e:
            logging.error(f"Error in draw_modules: {e}")
            logging.error(traceback.format_exc())

    def toggle_debug(self):
        """Toggle debug mode on/off"""
        self.debug_mode = not self.debug_mode
        logging.info(f"Debug mode {'enabled' if self.debug_mode else 'disabled'}")

    def update_modules(self):
        # Check for AI commands first
        if 'ai_module' in self.modules:
            while not self.modules['ai_module'].response_queue.empty():
                msg_type, content = self.modules['ai_module'].response_queue.get()
                if msg_type == 'command':
                    logging.info(f"Processing command: {content}")
                    self.module_manager.handle_command(content)
                    self.speech_logger.log_user_speech(content['text'], was_command=True)
                elif msg_type == 'speech':
                    self.speech_logger.log_user_speech(content['user_text'])
                    if content['ai_response']:
                        self.speech_logger.log_ai_response(content['ai_response'])
        
        # Update visible modules
        for module_name, module in self.modules.items():
            if self.module_manager.is_module_visible(module_name):
                try:
                    if self.state == "screensaver" and module_name not in CONFIG.get('screensaver_modules', ['retro_characters']):
                        continue
                    if self.state == "sleep" and module_name not in CONFIG.get('sleep_modules', []):
                        continue
                    if hasattr(module, 'update'):
                        module.update()
                except Exception as e:
                    logging.error(f"Error updating {module_name}: {e}")

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