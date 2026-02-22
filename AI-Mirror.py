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
from countdown_module import CountdownModule
from quote_module import QuoteModule
from news_module import NewsModule
from openclaw_module import OpenClawModule
from sysinfo_module import SysInfoModule
from greeting_module import GreetingModule
from api_tracker import api_tracker


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

        # Animation manager for fade transitions and center notifications
        from animation_manager import AnimationManager
        self.animation_manager = AnimationManager(
            self.screen.get_width(), self.screen.get_height()
        )

        # Wire notification callbacks for modules that support them
        for name, module in self.modules.items():
            if hasattr(module, 'set_notification_callback'):
                module.set_notification_callback(self.animation_manager.push_notification)

        # Ensure all modules have a visibility entry (don't override
        # decisions already made by ModuleManager.verify_voice_module)
        for module_name in self.modules.keys():
            if module_name not in self.module_manager.module_visibility:
                self.module_manager.module_visibility[module_name] = True

        # Auto-hide openclaw if no gateway configured
        if 'openclaw' in self.modules:
            oc = self.modules['openclaw']
            if not getattr(oc, 'gateway_url', ''):
                self.module_manager.module_visibility['openclaw'] = False
                logging.info("OpenClaw hidden: no gateway URL configured")

        # Auto-hide smarthome if no HA URL configured
        if 'smarthome' in self.modules:
            sh = self.modules['smarthome']
            if not getattr(sh, 'ha_url', ''):
                self.module_manager.module_visibility['smarthome'] = False
                logging.info("SmartHome hidden: no HA URL configured")

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
        """Initialize modules, skipping any disabled in module_visibility.

        Voice modules (ai_voice, ai_interaction, eleven_voice) open network
        connections on init and cost API credits, so they are only created
        when explicitly enabled in config.
        """
        modules = {}
        module_classes = {
            'clock': ClockModule,
            'weather': WeatherModule,
            'stocks': StocksModule,
            'calendar': CalendarModule,
            'fitbit': FitbitModule,
            'retro_characters': RetroCharactersModule,
            'ai_voice': AIVoiceModule,
            'ai_interaction': AIInteractionModule,
            'countdown': CountdownModule,
            'quote': QuoteModule,
            'news': NewsModule,
            'openclaw': OpenClawModule,
            'smarthome': SmartHomeModule,
            'sysinfo': SysInfoModule,
            'greeting': GreetingModule
        }

        config_copy = CONFIG.copy()
        visibility = CONFIG.get('module_visibility', {})

        for module_name, module_config in config_copy.items():
            if not isinstance(module_config, dict) or 'class' not in module_config:
                continue

            # Skip modules explicitly disabled in config (prevents network
            # connections like the OpenAI Realtime WebSocket from opening)
            if not visibility.get(module_name, True):
                logging.info(f"Skipping {module_name}: disabled in module_visibility")
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
        if 'fitbit' in config_copy and visibility.get('fitbit', True):
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
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
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
                elif event.key in (
                    pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5,
                    pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9, pygame.K_0,
                ):
                    self._toggle_module_by_key(event.key)
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
        """Draw all visible modules in z-order for mirror layout.

        State-aware: active draws info modules, screensaver draws retro chars,
        sleep draws clock only.
        """
        try:
            self.screen.fill((0, 0, 0))

            # Advance animation timers
            self.animation_manager.update()

            layout_v2 = CONFIG.get('layout_v2', {})
            left_names = layout_v2.get('left_modules', [])
            right_names = layout_v2.get('right_modules', [])
            center_names = layout_v2.get('center_overlay_modules', [])
            fullscreen_names = layout_v2.get('fullscreen_overlay_modules', [])
            screensaver_names = CONFIG.get('screensaver_modules', ['retro_characters'])

            if self.state == "screensaver":
                # Only draw screensaver overlays and clock
                for name in fullscreen_names:
                    if name in screensaver_names:
                        self._draw_module(name)
                self._draw_module('clock')

            elif self.state == "sleep":
                # Clock only
                self._draw_module('clock')

            else:
                # Active state: draw everything except screensaver
                # 1) Left and right column modules
                for name in left_names + right_names:
                    self._draw_module(name)

                # 2) Bottom bar: stock ticker
                if 'stocks' in self.modules and self.module_manager.is_module_visible('stocks'):
                    stocks = self.modules['stocks']
                    if hasattr(stocks, 'draw_scrolling_ticker'):
                        stocks.draw_scrolling_ticker(self.screen)
                        # Debug box for ticker (not drawn via _draw_module)
                        if self.debug_layout:
                            pos = self.module_positions.get('stocks', {})
                            sw = self.screen.get_width()
                            th = 40
                            ty = self.screen.get_height() - th
                            pygame.draw.rect(self.screen, (255, 0, 0),
                                            (0, ty, sw, th), 1)
                    else:
                        self._draw_module('stocks')

                # 3) Top bar: clock
                self._draw_module('clock')

                # 4) Center overlays (AI/voice - only when active)
                for name in center_names:
                    self._draw_module(name)

                # 5) Draw any remaining modules not in layout zones
                drawn = set(['clock', 'stocks'] + left_names + right_names
                            + center_names + fullscreen_names)
                for name in self.modules:
                    if name not in drawn:
                        self._draw_module(name)

            # Center notifications (on top of everything in all states)
            self.animation_manager.draw_notifications(self.screen)

            # Debug overlay
            if self.debug_layout:
                self._draw_debug_overlay()

            pygame.display.flip()
        except Exception as e:
            logging.error(f"Error in draw_modules: {e}")
            logging.error(traceback.format_exc())

    def _draw_module(self, name):
        """Draw a single module if it exists and is visible.

        Applies per-module fade alpha from the animation manager.
        When a module is mid-fade, it renders to a temp surface first.
        """
        if name not in self.modules:
            return
        if not self.module_manager.is_module_visible(name):
            return

        position = self.module_positions.get(name, {'x': 0, 'y': 0})
        module = self.modules[name]

        alpha = self.animation_manager.get_module_alpha(name)
        if alpha <= 0:
            return  # Fully faded out

        if self.animation_manager.is_module_fading(name):
            # Render to temp surface and apply alpha
            w = position.get('width', 300)
            h = position.get('height', 300)
            temp = pygame.Surface((w, h), pygame.SRCALPHA)
            temp_pos = dict(position, x=0, y=0)
            module.draw(temp, temp_pos)
            temp.set_alpha(alpha)
            self.screen.blit(temp, (position.get('x', 0), position.get('y', 0)))
        else:
            module.draw(self.screen, position)

        if self.debug_layout:
            try:
                w = position.get('width', 200)
                h = position.get('height', 100)
                pygame.draw.rect(self.screen, (255, 0, 0),
                                (position['x'], position['y'], w, h), 1)
                font = pygame.font.Font(None, 20)
                text = font.render(name, True, (255, 0, 0))
                self.screen.blit(text, (position['x'], position['y'] - 14))
            except Exception as e:
                logging.debug(f"Debug overlay error for {name}: {e}")

    def _draw_debug_overlay(self):
        """Draw debug grid and screen dimensions."""
        sw = self.screen.get_width()
        sh = self.screen.get_height()
        red = (255, 0, 0)
        pygame.draw.rect(self.screen, red, (0, 0, sw, sh), 1)
        cx, cy = sw // 2, sh // 2
        pygame.draw.line(self.screen, red, (cx, 0), (cx, sh), 1)
        pygame.draw.line(self.screen, red, (0, cy), (sw, cy), 1)
        debug_font = pygame.font.Font(None, 20)
        dims = debug_font.render(f"{sw}x{sh}", True, red)
        self.screen.blit(dims, (10, sh - 20))

    def toggle_debug(self):
        """Toggle debug mode on/off (includes visible layout grid)."""
        self.debug_mode = not self.debug_mode
        self.debug_layout = self.debug_mode
        logging.info(f"Debug mode {'enabled' if self.debug_mode else 'disabled'}")

    def _toggle_module_by_key(self, key):
        """Toggle module visibility via number key (1-9, 0=10th)."""
        key_map = {
            pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3,
            pygame.K_5: 4, pygame.K_6: 5, pygame.K_7: 6, pygame.K_8: 7,
            pygame.K_9: 8, pygame.K_0: 9,
        }
        idx = key_map.get(key)
        if idx is None:
            return

        toggle_list = CONFIG.get('toggle_modules', [])
        if idx >= len(toggle_list):
            return

        module_name = toggle_list[idx]
        if module_name not in self.modules:
            return

        current = self.module_manager.is_module_visible(module_name)
        self.module_manager.module_visibility[module_name] = not current
        state = "ON" if not current else "OFF"
        logging.info(f"Toggled {module_name}: {state} (key {idx + 1})")

        # Show on-screen toast via center notification
        self.animation_manager.push_notification(
            f"[{idx + 1}] {module_name}: {state}",
            duration_ms=2000,
        )

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

        # Update visible modules (state-aware)
        screensaver_names = CONFIG.get('screensaver_modules', ['retro_characters'])
        sleep_names = CONFIG.get('sleep_modules', ['clock'])
        for module_name, module in self.modules.items():
            if self.module_manager.is_module_visible(module_name):
                try:
                    if self.state == "active" and module_name in screensaver_names:
                        continue  # Don't update screensaver during active
                    if self.state == "screensaver" and module_name not in screensaver_names and module_name != 'clock':
                        continue
                    if self.state == "sleep" and module_name not in sleep_names:
                        continue
                    if hasattr(module, 'update'):
                        module.update()
                except Exception as e:
                    logging.error(f"Error updating {module_name}: {e}")

        # Feed weather summary to clock top-bar status line
        if 'clock' in self.modules and 'weather' in self.modules:
            weather = self.modules['weather']
            clock = self.modules['clock']
            if hasattr(clock, 'set_status_indicators') and weather.weather_data:
                try:
                    temp = weather.weather_data['main']['temp']
                    cond = weather.weather_data['weather'][0]['description']
                    clock.set_status_indicators(f"{temp:.0f}C  {cond}")
                except Exception:
                    pass

    def run(self):
        """Run the main application loop."""
        import signal
        signal.signal(signal.SIGINT, lambda s, f: setattr(self, 'running', False))

        try:
            logging.info("Starting Magic Mirror main loop")
            while self.running:
                try:
                    self.handle_events()
                    self.update_modules()
                    self.draw_modules()
                    self.clock.tick(self.frame_rate)
                except KeyboardInterrupt:
                    logging.info("Ctrl+C received")
                    self.running = False
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
        api_tracker.force_summary()

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
        """Initialize screen using native display resolution.

        Auto-detects the actual display size so modules are never drawn
        off-screen, regardless of what CURRENT_MONITOR says in config.
        """
        pygame.display.set_caption("Magic Mirror")
        pygame.mouse.set_visible(False)

        # Detect native display resolution before creating the surface
        display_info = pygame.display.Info()
        native_w = display_info.current_w
        native_h = display_info.current_h
        logging.info(f"Native display resolution: {native_w}x{native_h}")

        config_w = CONFIG.get('current_monitor', {}).get('width', 800)
        config_h = CONFIG.get('current_monitor', {}).get('height', 480)
        if native_w != config_w or native_h != config_h:
            logging.warning(
                f"Config says {config_w}x{config_h} but display is "
                f"{native_w}x{native_h} -- using actual display size"
            )

        # Use (0,0) to let pygame pick native resolution in fullscreen
        display_configs = [
            (pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF, "hardware accelerated"),
            (pygame.FULLSCREEN | pygame.NOFRAME, "no frame"),
            (pygame.FULLSCREEN, "basic fullscreen"),
        ]

        self.screen = None
        for flags, desc in display_configs:
            try:
                self.screen = pygame.display.set_mode((0, 0), flags)
                break
            except Exception as e:
                logging.warning(f"Failed {desc} mode: {e}")

        if not self.screen:
            self.screen = pygame.display.set_mode((native_w, native_h))
            logging.warning(f"Using fallback windowed mode: {native_w}x{native_h}")

        # Read back actual surface dimensions
        actual_w = self.screen.get_width()
        actual_h = self.screen.get_height()
        logging.info(f"Screen initialized: {actual_w}x{actual_h}")

        # Update CONFIG so all downstream code (layout, modules) uses real size
        CONFIG['current_monitor']['width'] = actual_w
        CONFIG['current_monitor']['height'] = actual_h

        # Update module params that depend on screen size
        if 'weather' in CONFIG and 'params' in CONFIG['weather']:
            CONFIG['weather']['params']['screen_width'] = actual_w
            CONFIG['weather']['params']['screen_height'] = actual_h
        if 'retro_characters' in CONFIG and 'params' in CONFIG['retro_characters']:
            CONFIG['retro_characters']['params']['screen_size'] = (actual_w, actual_h)

        self.layout_manager = LayoutManager(actual_w, actual_h)

    def change_state(self, new_state):
        """Change mirror state with fade transition."""
        if self.state == new_state:
            return
        old_state = self.state
        self.state = new_state
        self.animation_manager.begin_state_transition(old_state, new_state)
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
                col_w = int(width * 0.22)
                right_x = width - col_w - 15
                fallback_positions = {
                    'clock': {'x': 0, 'y': 0, 'width': width, 'height': 80},
                    'stocks': {'x': 0, 'y': height - 50, 'width': width, 'height': 50},
                    'weather': {'x': 15, 'y': 95, 'width': col_w, 'height': 250},
                    'calendar': {'x': 15, 'y': 360, 'width': col_w, 'height': 250},
                    'countdown': {'x': 15, 'y': 625, 'width': col_w, 'height': 250},
                    'news': {'x': right_x, 'y': 95, 'width': col_w, 'height': 200},
                    'quote': {'x': right_x, 'y': 310, 'width': col_w, 'height': 200},
                    'fitbit': {'x': right_x, 'y': 525, 'width': col_w, 'height': 200},
                    'openclaw': {'x': right_x, 'y': 740, 'width': col_w, 'height': 200},
                    'smarthome': {'x': 15, 'y': 890, 'width': col_w, 'height': 200},
                    'sysinfo': {'x': right_x, 'y': 955, 'width': col_w, 'height': 150},
                    'greeting': {'x': right_x, 'y': 95, 'width': col_w, 'height': 150},
                    'retro_characters': {'x': 0, 'y': 0, 'width': width, 'height': height},
                    'ai_interaction': {'x': col_w + 30, 'y': height // 3, 'width': width - col_w * 2 - 60, 'height': 200},
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
