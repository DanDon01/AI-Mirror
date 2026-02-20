#  Code for the main Magic Mirror application that runs on the Raspberry Pi
#  This code is responsible for initializing the modules, handling events,
#  updating the modules, and drawing the modules on the screen.
#  It also handles toggling between active, screensaver, and sleep states.
#  The main loop runs until the user closes the application.

import os
import sys
import ctypes
import ctypes.util
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import time
import traceback
import warnings

# --- Audio environment setup (must happen before pygame/pyaudio imports) ---
# These environment variables configure ALSA and audio drivers on the Pi.
os.environ["PYTHONUNBUFFERED"] = "1"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
os.environ["JACK_NO_START_SERVER"] = "1"
os.environ["JACK_NO_AUDIO_RESERVATION"] = "1"
os.environ["ALSA_CARD"] = "2"
os.environ["AUDIODEV"] = "hw:2,0"
os.environ["PULSE_SERVER"] = "localhost"
os.environ["PORTAUDIO_ENABLE_DEVICE_ENUMERATION"] = "0"

# Use real ALSA config for audio functionality, dummy SDL driver for pygame init
os.environ["ALSA_CONFIG_PATH"] = "/usr/share/alsa/alsa.conf"
os.environ["SDL_AUDIODRIVER"] = "dummy"

# --- Stderr filtering for ALSA/JACK noise during import ---
real_stderr = sys.stderr

class FilteredStderr:
    """Filter out ALSA, JACK, and audio subsystem noise from stderr."""
    FILTER_KEYWORDS = [
        "ALSA", "alsa", "pcm", "snd_", "jack", "Jack", "JackShm",
        "Cannot connect", "socket", "pulse", "hdmi", "recognize_legacy"
    ]

    def write(self, message):
        if not any(keyword in message for keyword in self.FILTER_KEYWORDS):
            real_stderr.write(message)

    def flush(self):
        real_stderr.flush()

sys.stderr = FilteredStderr()

# --- Silence ALSA error handler via C library ---
try:
    alsa_lib = ctypes.CDLL(ctypes.util.find_library('asound') or 'libasound.so')
    ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
    )
    def _silent_error_handler(filename, line, function, err, fmt):
        pass
    c_error_handler = ERROR_HANDLER_FUNC(_silent_error_handler)
    alsa_lib.snd_lib_error_set_handler(c_error_handler)
except Exception as e:
    logging.warning(f"Failed to set ALSA error handler: {e}")

# --- Now safe to import audio-related libraries ---
import pygame
import pyaudio
import speech_recognition

# Restore stderr after audio imports
sys.stderr = sys.__stderr__

warnings.filterwarnings("ignore", category=RuntimeWarning)

# --- Project imports ---
from config import CONFIG
from calendar_module import CalendarModule
from weather_module import WeatherModule
from fitbit_module import FitbitModule
from smarthome_module import SmartHomeModule
from stocks_module import StocksModule
from clock_module import ClockModule
from retrocharacters_module import RetroCharactersModule
from module_manager import ModuleManager
from layout_manager import LayoutManager
from AI_Module import AIInteractionModule
from ai_voice_module import AIVoiceModule


def ensure_valid_color(color):
    """Ensure a color value is valid for pygame."""
    if color is None:
        return (200, 200, 200)

    if isinstance(color, tuple) and len(color) >= 3:
        return (int(color[0]), int(color[1]), int(color[2]))

    if isinstance(color, str) and color.startswith('#'):
        try:
            if len(color) == 4:
                r = int(color[1] * 2, 16)
                g = int(color[2] * 2, 16)
                b = int(color[3] * 2, 16)
            elif len(color) == 7:
                r = int(color[1:3], 16)
                g = int(color[3:5], 16)
                b = int(color[5:7], 16)
            else:
                return (200, 200, 200)
            return (r, g, b)
        except ValueError:
            pass

    return (200, 200, 200)


class SpeechLogger:
    def __init__(self):
        self.speech_logger = logging.getLogger('speech_logger')
        self.speech_logger.setLevel(logging.INFO)

        speech_handler = RotatingFileHandler(
            'speech_history.log',
            maxBytes=1000000,
            backupCount=5
        )

        formatter = logging.Formatter('%(asctime)s - %(message)s')
        speech_handler.setFormatter(formatter)

        self.speech_logger.propagate = False
        self.speech_logger.addHandler(speech_handler)

    def log_user_speech(self, text, was_command=False):
        """Log what the user said."""
        if was_command:
            self.speech_logger.info(f"USER COMMAND: {text}")
        else:
            self.speech_logger.info(f"USER: {text}")

    def log_ai_response(self, text):
        """Log what the AI responded."""
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

        # Initialize modules first
        self.modules = self.initialize_modules()

        self.frame_rate = CONFIG.get('frame_rate', 30)
        self.running = True
        self.state = "active"
        self.font = pygame.font.Font(None, 48)

        # Create module manager with pre-initialized modules
        self.module_manager = ModuleManager(initialized_modules=self.modules)

        # Prevent module_manager from re-initializing
        self.module_manager.initialize_modules = lambda: None
        self.module_manager.initialize_module = lambda x: None

        self._positions_initialized = False

        # Initialize layout manager for proper module positioning
        self.layout_manager = LayoutManager(self.screen.get_width(), self.screen.get_height())

        self.debug_layout = CONFIG.get('debug', {}).get('show_layout', False)

        self.module_positions = {}
        self.setup_module_positions()

        # Initialize module visibility
        for module_name in self.modules.keys():
            self.module_manager.module_visibility[module_name] = True
        logging.info(f"Initialized modules: {list(self.modules.keys())}")

    def setup_logging(self):
        """Set up logging configuration."""
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        file_handler = RotatingFileHandler(
            'magic_mirror.log',
            maxBytes=1000000,
            backupCount=5
        )

        console_handler = logging.StreamHandler()

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        log_level = CONFIG.get('debug', {}).get('log_level', 'INFO')
        root_logger.setLevel(getattr(logging, log_level))

        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

        logging.getLogger('speech_logger').propagate = False

    def debug_log(self, message):
        """Helper method for debug logging."""
        if self.debug_mode:
            logging.debug(message)

    def initialize_modules(self):
        """Initialize modules with explicit priority for ai_voice."""
        modules = {}
        module_classes = {
            'clock': ClockModule,
            'weather': WeatherModule,
            'stocks': StocksModule,
            'calendar': CalendarModule,
            'fitbit': FitbitModule,
            'retro_characters': RetroCharactersModule,
            'ai_voice': AIVoiceModule,
            'ai_interaction': AIInteractionModule
        }

        config_copy = CONFIG.copy()

        for module_name, module_config in config_copy.items():
            if not isinstance(module_config, dict) or 'class' not in module_config:
                continue
            try:
                if module_name == 'ai_voice':
                    logging.info(f"Attempting to initialize primary voice module: {module_name}")
                    modules[module_name] = module_classes[module_name](module_config)
                    logging.info(f"Successfully initialized {module_name}")
                elif module_name == 'ai_interaction' and 'ai_voice' not in modules:
                    logging.info("Falling back to AIInteractionModule")
                    modules[module_name] = module_classes[module_name](module_config)
                    logging.info(f"Initialized fallback module: {module_name}")
                elif module_name in module_classes and module_name != 'fitbit':
                    modules[module_name] = module_classes[module_name](**module_config.get('params', {}))
                    logging.info(f"Initialized module: {module_name}")
            except Exception as e:
                logging.error(f"Error initializing {module_name}: {e}")
                logging.error(traceback.format_exc())
                if module_name == 'ai_voice':
                    logging.warning("Primary voice module failed, attempting fallback")

        # Initialize Fitbit last (depends on network, can be slow)
        if 'fitbit' in config_copy:
            try:
                logging.info("Initializing FitbitModule (delayed)")
                modules['fitbit'] = module_classes['fitbit'](**config_copy['fitbit'].get('params', {}))
                logging.info("Successfully initialized FitbitModule")
            except Exception as e:
                logging.error(f"Error initializing fitbit: {e}")

        return modules

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    self.running = False
                elif event.key == pygame.K_d:
                    self.toggle_debug()
                elif event.key == pygame.K_s:
                    if self.state == "active":
                        self.change_state("screensaver")
                    elif self.state == "screensaver":
                        self.change_state("sleep")
                    else:
                        self.change_state("active")
                elif event.key == pygame.K_SPACE:
                    if self.state != "active":
                        self.change_state("active")
                    elif 'ai_voice' in self.modules:
                        try:
                            logging.info("Space bar pressed - triggering AIVoiceModule")
                            self.modules['ai_voice'].on_button_press()
                        except Exception as e:
                            logging.error(f"Error triggering AIVoiceModule: {e}")
                            if 'ai_interaction' in self.modules:
                                logging.info("Falling back to AIInteractionModule")
                                self.modules['ai_interaction'].on_button_press()
                    elif 'ai_interaction' in self.modules:
                        logging.info("Using AIInteractionModule (primary voice unavailable)")
                        self.modules['ai_interaction'].on_button_press()

    def draw_modules(self):
        """Draw all visible modules to the screen."""
        try:
            self.screen.fill((0, 0, 0))

            for name, module in self.modules.items():
                if name in self.module_manager.module_visibility:
                    if self.module_manager.module_visibility[name]:
                        position = self.module_positions.get(name, {'x': 0, 'y': 0})

                        if isinstance(position, dict) and 'x' in position and 'y' in position:
                            pos_tuple = (position['x'], position['y'])
                        else:
                            pos_tuple = position

                        module.draw(self.screen, pos_tuple)

                        if self.debug_layout:
                            try:
                                pos = position
                                width = pos.get('width', 200)
                                height = pos.get('height', 100)
                                pygame.draw.rect(self.screen, (255, 0, 0),
                                                (pos['x'], pos['y'], width, height), 2)
                                font = pygame.font.Font(None, 24)
                                text = font.render(name, True, (255, 0, 0))
                                self.screen.blit(text, (pos['x'], pos['y'] - 20))
                            except Exception as e:
                                logging.debug(f"Debug overlay error for {name}: {e}")

            if self.debug_layout:
                pygame.draw.rect(self.screen, (255, 0, 0),
                                (0, 0, self.screen.get_width(), self.screen.get_height()), 1)
                center_x = self.screen.get_width() // 2
                center_y = self.screen.get_height() // 2
                pygame.draw.line(self.screen, (255, 0, 0),
                                (center_x, 0), (center_x, self.screen.get_height()), 1)
                pygame.draw.line(self.screen, (255, 0, 0),
                                (0, center_y), (self.screen.get_width(), center_y), 1)
                debug_font = pygame.font.Font(None, 24)
                dims_text = debug_font.render(
                    f"Screen: {self.screen.get_width()}x{self.screen.get_height()}",
                    True, (255, 0, 0))
                self.screen.blit(dims_text, (10, self.screen.get_height() - 30))

            pygame.display.flip()
        except Exception as e:
            logging.error(f"Error in draw_modules: {e}")
            logging.error(traceback.format_exc())

    def toggle_debug(self):
        """Toggle debug mode on/off."""
        self.debug_mode = not self.debug_mode
        logging.info(f"Debug mode {'enabled' if self.debug_mode else 'disabled'}")

    def update_modules(self):
        # Check for AI commands
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
        """Run the main application loop."""
        try:
            logging.info("Starting Magic Mirror main loop")
            while self.running:
                try:
                    self.handle_events()
                    self.update_modules()
                    self.draw_modules()
                    self.clock.tick(self.frame_rate)
                except Exception as e:
                    logging.error(f"Error in main loop iteration: {e}")
                    logging.error(traceback.format_exc())
                    time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Received shutdown signal")
        except Exception as e:
            logging.error(f"Fatal error in main loop: {e}")
            logging.error(traceback.format_exc())
        finally:
            self.cleanup()
            pygame.quit()
            logging.info("Magic Mirror shutdown complete")
            sys.exit(0)

    def cleanup(self):
        """Safely clean up all resources."""
        logging.info("Shutting down Magic Mirror")

        module_names = list(self.modules.keys())
        module_names.reverse()

        for module_name in module_names:
            try:
                module = self.modules[module_name]
                if hasattr(module, 'cleanup'):
                    logging.info(f"Cleaning up module: {module_name}")
                    module.cleanup()
            except Exception as e:
                logging.error(f"Error cleaning up module {module_name}: {e}")

        pygame.mixer.quit()
        pygame.quit()

    def initialize_screen(self):
        """Initialize screen with robust fullscreen handling."""
        pygame.display.set_caption("Magic Mirror")
        pygame.mouse.set_visible(False)

        width = CONFIG.get('current_monitor', {}).get('width', 800)
        height = CONFIG.get('current_monitor', {}).get('height', 480)

        display_configs = [
            (pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF, "hardware accelerated"),
            (pygame.FULLSCREEN | pygame.NOFRAME, "no frame"),
            (pygame.FULLSCREEN, "basic fullscreen")
        ]

        self.screen = None
        for flags, desc in display_configs:
            try:
                self.screen = pygame.display.set_mode((width, height), flags)
                logging.info(f"Screen initialized with {desc} mode: {width}x{height}")
                break
            except Exception as e:
                logging.warning(f"Failed {desc} mode: {e}")

        if not self.screen:
            self.screen = pygame.display.set_mode((width, height))
            logging.warning(f"Using fallback windowed mode: {width}x{height}")

        self.layout_manager = LayoutManager(width, height)

    def change_state(self, new_state):
        """Change mirror state and update module visibility."""
        if self.state == new_state:
            return
        self.state = new_state
        logging.info(f"Mirror state changed to: {new_state}")

    def setup_module_positions(self):
        """Set up module positions based on the layout from config."""
        if hasattr(self, '_positions_initialized') and self._positions_initialized:
            logging.info("Module positions already initialized, skipping")
            return

        try:
            for name in self.modules.keys():
                position = self.layout_manager.get_module_position(name)
                if position:
                    self.module_positions[name] = position
                    logging.info(f"Position for {name}: {position}")
                else:
                    logging.warning(f"No position defined for module: {name}")

            missing_positions = [name for name in self.modules.keys() if name not in self.module_positions]
            if missing_positions:
                logging.warning(f"Modules missing positions: {missing_positions}")

                width, height = self.screen.get_size()
                fallback_positions = {
                    'clock': {'x': 20, 'y': 20, 'width': 300, 'height': 100},
                    'weather': {'x': width - 320, 'y': 20, 'width': 300, 'height': 200},
                    'calendar': {'x': 20, 'y': 150, 'width': 400, 'height': 300},
                    'stocks': {'x': 20, 'y': height - 150, 'width': 400, 'height': 130},
                    'fitbit': {'x': width - 320, 'y': 240, 'width': 300, 'height': 200},
                    'retro_characters': {'x': width // 2 - 150, 'y': height // 2 - 150, 'width': 300, 'height': 300},
                    'ai_interaction': {'x': width // 2 - 200, 'y': height - 200, 'width': 400, 'height': 180}
                }

                for name in missing_positions:
                    if name in fallback_positions:
                        self.module_positions[name] = fallback_positions[name]
                        logging.info(f"Using fallback position for {name}")
                    else:
                        idx = missing_positions.index(name)
                        self.module_positions[name] = {'x': 10, 'y': 10 + idx * 100, 'width': 300, 'height': 90}
                        logging.info(f"Using generic position for {name}")

            self._positions_initialized = True

        except Exception as e:
            logging.error(f"Error setting up module positions: {e}")
            for i, name in enumerate(self.modules.keys()):
                self.module_positions[name] = {'x': 10, 'y': 10 + i * 100, 'width': 300, 'height': 90}
                logging.warning(f"Using emergency fallback position for {name}")


if __name__ == "__main__":
    mirror = MagicMirror()
    mirror.run()
