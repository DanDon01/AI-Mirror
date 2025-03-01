#  Code for the main Magic Mirror application that runs on the Raspberry Pi
#  This code is responsible for initializing the modules, handling events, updating the modules, and drawing the modules on the screen
#  It also handles toggling between active, screensaver, and sleep states, and toggling debug mode on/off
#  The main loop runs until the user closes the application

# Block JACK server completely
import os
import sys

# Create a pipe to completely filter audio-related stderr messages
real_stderr = sys.stderr

# Create a more aggressive filter for stderr
class EnhancedFilteredStderr:
    def write(self, message):
        # Filter out ALSA, JACK, pcm, sound-related errors completely
        if not any(x in message for x in [
            "ALSA", "alsa", "pcm", "snd_", "jack", "Jack", "JackShm", 
            "Cannot connect", "socket", "pulse", "audio", "sound",
            "hdmi", "device", "hw", "recognize_legacy"
        ]):
            real_stderr.write(message)
    
    def flush(self):
        real_stderr.flush()

# Replace stderr with our enhanced filtered version
sys.stderr = EnhancedFilteredStderr()

# Completely silence audio errors
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
os.environ['ALSA_CARD'] = '2'  # Use card 2 (USB PnP Sound Device)
os.environ['PYTHONUNBUFFERED'] = '1'

# More aggressive environment settings to reduce errors
os.environ['ALSA_CONFIG_PATH'] = '/dev/null'
os.environ['JACK_NO_START_SERVER'] = '1'
os.environ['JACK_NO_AUDIO_RESERVATION'] = '1'

# Set environment variables to make PyAudio safer
os.environ['AUDIODEV'] = '/dev/null'  # Force null audio device
os.environ['SDL_AUDIODRIVER'] = 'dummy'  # Use dummy audio driver
os.environ['PULSE_SERVER'] = 'localhost'  # Avoid network audio issues

# Make sure Python logging still works by setting up a basic logger
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Log to stdout instead of stderr
    ]
)

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

# Now import the problematic libraries
import pygame
import pyaudio
import speech_recognition

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

# Mock problematic audio libraries before they're imported
import sys

class MockPyAudio:
    # Add necessary constants
    paInt16 = 8
    paFloat32 = 32
    paInt32 = 16
    
    @staticmethod
    def get_sample_size(format_type):
        """Mock implementation of get_sample_size"""
        if format_type == MockPyAudio.paInt16:
            return 2
        elif format_type == MockPyAudio.paFloat32:
            return 4
        elif format_type == MockPyAudio.paInt32:
            return 4
        return 2  # Default to 2 bytes
    
    class PyAudio:
        def __init__(self): 
            print("MOCK: Safe PyAudio initialized")
            
        def get_device_count(self):
            return 3  # Pretend we have 3 devices
            
        def get_host_api_info_by_index(self, index): 
            return {"deviceCount": 3}
            
        def get_device_info_by_index(self, index): 
            if index == 2:  # Our USB microphone
                return {
                    "name": "Mock USB PnP Sound Device", 
                    "maxInputChannels": 2,
                    "defaultSampleRate": 44100
                }
            return {"name": "Mock Device", "maxInputChannels": 0}
            
        def terminate(self): 
            pass

# Replace PyAudio with our mock before anything imports it
sys.modules['pyaudio'] = MockPyAudio

def ensure_valid_color(color):
    """Ensure a color value is valid for pygame"""
    if color is None:
        return (200, 200, 200)  # Default gray
    
    if isinstance(color, tuple) and len(color) >= 3:
        # Make sure all values are integers
        return (int(color[0]), int(color[1]), int(color[2]))
    
    if isinstance(color, str):
        # Try to convert from hex
        if color.startswith('#') and len(color) in (4, 7):
            try:
                if len(color) == 4:
                    r = int(color[1] + color[1], 16)
                    g = int(color[2] + color[2], 16)
                    b = int(color[3] + color[3], 16)
                else:
                    r = int(color[1:3], 16)
                    g = int(color[3:5], 16)
                    b = int(color[5:7], 16)
                return (r, g, b)
            except:
                pass
    
    # Fallback default
    return (200, 200, 200)

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
        self.initialize_screen()
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
            
            # Debug layout flag - make this false to disable red boxes
            self.debug_layout = True
            
            # Draw only visible modules
            for module_name, module in self.modules.items():
                self.debug_log(f"Attempting to draw {module_name}")
                if self.module_manager.is_module_visible(module_name):
                    try:
                        position = self.layout_manager.get_module_position(module_name)
                        if position:
                            # Fix: ensure position is correctly formatted
                            if isinstance(position, dict) and 'x' in position and 'y' in position:
                                pos_tuple = (position['x'], position['y'])
                            else:
                                pos_tuple = position
                            
                            self.debug_log(f"Drawing {module_name} at position {pos_tuple}")
                            module.draw(self.screen, pos_tuple)
                        else:
                            logging.warning(f"No position defined for {module_name}")
                    except Exception as e:
                        if not hasattr(self, f'_reported_{module_name}'):
                            logging.error(f"Error drawing module {module_name}: {str(e)}")
                            logging.error(traceback.format_exc())
                            setattr(self, f'_reported_{module_name}', True)
            
            if hasattr(self, 'debug_layout') and getattr(self, 'debug_layout', False):
                for name, module in self.modules.items():
                    # Skip rendering debug overlay for full-screen modules
                    if name == 'retro_characters':
                        continue
                        
                    try:
                        pos = self.layout_manager.get_module_position(name)
                        if isinstance(pos, dict) and 'x' in pos and 'y' in pos:
                            # Use width/height from position if available
                            width = pos.get('width', 200)
                            height = pos.get('height', 100)
                            
                            # Draw red rectangle around module area
                            pygame.draw.rect(self.screen, (255, 0, 0), 
                                            (pos['x'], pos['y'], width, height), 2)
                            # Draw module name for identification
                            font = pygame.font.Font(None, 24)
                            text = font.render(name, True, (255, 0, 0))
                            self.screen.blit(text, (pos['x'], pos['y'] - 20))
                    except Exception as e:
                        logging.debug(f"Debug overlay error for {name}: {e}")
            
            # Visual debug for screen boundaries
            if self.debug_layout:
                # Draw screen boundaries
                pygame.draw.rect(self.screen, (255, 0, 0), 
                                (0, 0, self.screen.get_width(), self.screen.get_height()), 1)
                
                # Draw center crosshair
                center_x = self.screen.get_width() // 2
                center_y = self.screen.get_height() // 2
                pygame.draw.line(self.screen, (255, 0, 0), (center_x, 0), (center_x, self.screen.get_height()), 1)
                pygame.draw.line(self.screen, (255, 0, 0), (0, center_y), (self.screen.get_width(), center_y), 1)
                
                # Draw dimension text
                debug_font = pygame.font.Font(None, 24)
                dims_text = debug_font.render(f"Screen: {self.screen.get_width()}x{self.screen.get_height()}", True, (255, 0, 0))
                self.screen.blit(dims_text, (10, self.screen.get_height() - 30))
            
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

    def initialize_screen(self):
        """Force fullscreen with multiple hardware-specific options"""
        # Set display modes for fullscreen
        pygame.display.set_caption("Magic Mirror")
        pygame.mouse.set_visible(False)  # Hide cursor
        
        # Get screen dimensions from config
        config_screen = CONFIG.get('current_monitor', {})
        width = config_screen.get('width', 800)  # Default to 800 for safety
        height = config_screen.get('height', 480)  # Default to 480 for safety
        
        # Log the configured dimensions
        logging.info(f"Using screen dimensions: {width}x{height}")
        
        # Try multiple approaches to force fullscreen
        fullscreen_flags = [
            pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF,
            pygame.FULLSCREEN | pygame.NOFRAME,
            pygame.FULLSCREEN
        ]
        
        for flags in fullscreen_flags:
            try:
                logging.info(f"Trying fullscreen mode with flags: {flags}")
                self.screen = pygame.display.set_mode((width, height), flags)
                actual_size = self.screen.get_size()
                logging.info(f"Screen created with size: {actual_size[0]}x{actual_size[1]}")
                break
            except Exception as e:
                logging.error(f"Failed to set fullscreen with flags {flags}: {e}")
        
        # If all fullscreen attempts failed, try a final fallback
        if not hasattr(self, 'screen') or self.screen is None:
            logging.warning("Fullscreen attempts failed, using basic mode")
            self.screen = pygame.display.set_mode((width, height))
        
        # Setup layout manager with correct dimensions
        self.layout_manager = LayoutManager(width, height)
        self.debug_layout = True  # Enable debug overlay to see boundaries

if __name__ == "__main__":
    mirror = MagicMirror()
    mirror.run()