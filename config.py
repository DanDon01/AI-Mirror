from dotenv import load_dotenv
import os
from datetime import time
import pygame

# Initialize pygame to access font information
pygame.font.init()

# Get the directory of the current file (config.py)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the path to Variables.env in the parent directory
env_path = os.path.join(current_dir, '..', 'Variables.env')

# Load the .env file
load_dotenv(env_path)

#########################################
# GLOBAL CONSTANTS
#########################################

# Mirror-optimized color palette
# Pure black = transparent through two-way mirror glass
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)

# Text hierarchy: platinum on black for the minimal-luxury mirror look.
# Primary is bright enough to read through glass; secondary and dim
# recede so key values carry the layout.
COLOR_TEXT_PRIMARY = (226, 228, 232)
COLOR_TEXT_SECONDARY = (148, 150, 156)
COLOR_TEXT_DIM = (96, 98, 104)
COLOR_TEXT_ACCENT = (100, 180, 255)

# Single luxury accent: soft champagne. Used for module labels, hairline
# rules, and small emphasis only - never large areas.
COLOR_ACCENT_PRIMARY = (196, 174, 128)

# Module title color (legacy name; now the champagne accent)
COLOR_TITLE_BLUE = COLOR_ACCENT_PRIMARY

# Clock face: bright platinum, not cyan - reads as engraved, not digital
COLOR_CLOCK_FACE = (232, 234, 238)

# Functional accent colors, muted to sit quietly on glass
COLOR_ACCENT_BLUE = (110, 150, 210)
COLOR_ACCENT_GREEN = (124, 188, 150)
COLOR_ACCENT_RED = (206, 118, 118)
COLOR_ACCENT_AMBER = (212, 178, 122)

# Separator lines (subtle dividers between sections)
COLOR_SEPARATOR = (40, 40, 40)

# Legacy aliases -- modules import these names
COLOR_FONT_DEFAULT = COLOR_TEXT_PRIMARY
COLOR_FONT_TITLE = COLOR_TEXT_DIM
COLOR_FONT_SUBTITLE = COLOR_TEXT_SECONDARY
COLOR_FONT_BODY = COLOR_TEXT_PRIMARY
COLOR_FONT_SMALL = COLOR_TEXT_SECONDARY
COLOR_PASTEL_GREEN = COLOR_ACCENT_GREEN
COLOR_PASTEL_RED = COLOR_ACCENT_RED
COLOR_PASTEL_BLUE = COLOR_ACCENT_BLUE

# Module backgrounds: fully transparent on mirror (no visible boxes)
COLOR_BG_MODULE = (0, 0, 0)
COLOR_BG_HEADER = (0, 0, 0)
COLOR_BG_HIGHLIGHT = (0, 0, 0)
COLOR_BG_MODULE_ALPHA = (0, 0, 0, 0)
COLOR_BG_HEADER_ALPHA = (0, 0, 0, 0)

# Text transparency (high = more visible, critical for mirror readability)
TRANSPARENCY = 240

# Typography -- Lato (bundled in assets/fonts, OFL licensed) gives the
# same premium light weights on Windows and the Pi. SysFont names remain
# as a fallback if the TTFs are missing.
FONT_NAME = "segoeui,dejavusans,freesans,arial"
FONT_NAME_CLOCK = "consolas,dejavusansmono,liberationmono,couriernew,monospace"

_FONTS_DIR = os.path.join(current_dir, 'assets', 'fonts')
_FONT_FILES = {
    'light': 'Lato-Light.ttf',
    'regular': 'Lato-Regular.ttf',
    'bold': 'Lato-Bold.ttf',
}
_font_cache = {}


def load_font(weight, size):
    """Return a Font for ('light'|'regular'|'bold', px). Cached.

    Falls back to the system font stack when the bundled TTF is missing.
    """
    key = (weight, size)
    font = _font_cache.get(key)
    if font is None:
        path = os.path.join(_FONTS_DIR, _FONT_FILES.get(weight, 'Lato-Regular.ttf'))
        try:
            font = pygame.font.Font(path, size)
        except Exception:
            font = pygame.font.SysFont(FONT_NAME, size)
        _font_cache[key] = font
    return font


FONT_SIZE_CLOCK = 84
FONT_SIZE_HERO = 56       # large feature values (temperature, etc.)
FONT_SIZE_TITLE = 28
FONT_SIZE_SUBTITLE = 22
FONT_SIZE_BODY = 19
FONT_SIZE_SMALL = 14
FONT_SIZE_LABEL = 13      # tracked uppercase module labels
FONT_SIZE_TICKER = 20
FONT_SIZE = FONT_SIZE_BODY

# Letterspacing (px) for tracked uppercase labels
LABEL_TRACKING = 4

# Spacing and Dimensions
LINE_SPACING = 30
DEFAULT_PADDING = 12
DEFAULT_LINE_HEIGHT = 28
DEFAULT_RADIUS = 0  # No rounded rects on transparent backgrounds

# Standard screen dimensions
SCREEN_WIDTH_DEFAULT = 800
SCREEN_HEIGHT_DEFAULT = 1280

# Paths for assets and data
assets_dir = os.path.join(current_dir, 'assets')
retro_icons_path = os.path.join(assets_dir, 'retro_icons')
weather_icons_path = os.path.join(assets_dir, 'weather_icons')
sound_effects_path = os.path.join(assets_dir, 'sound_effects')
data_dir = os.path.join(current_dir, 'data')

#########################################
# MONITOR CONFIGURATIONS
#########################################

SCREEN_PADDING = 20
MODULE_SPACING = 10

MONITOR_CONFIGS = {
    '27_portrait': {
        'resolution': (1440, 2560),
        'module_scale': 1.0,
        'font_scale': 1.0,
        'left_col_width': 320,
        'right_col_width': 320,
    },
    '24_portrait': {
        'resolution': (1200, 1920),
        'module_scale': 0.833,
        'font_scale': 0.85,
        'left_col_width': 265,
        'right_col_width': 265,
    },
    '21_portrait': {
        'resolution': (768, 1024),
        'module_scale': 0.533,
        'font_scale': 0.65,
        'left_col_width': 170,
        'right_col_width': 170,
    }
}

CURRENT_MONITOR = MONITOR_CONFIGS['27_portrait']

#########################################
# LAYOUT CONFIGURATION
#########################################

LAYOUT = {
    'screen_padding': int(30 * CURRENT_MONITOR['module_scale']),
    'module_spacing': int(15 * CURRENT_MONITOR['module_scale']),
    'module_sizes': {
        'standard': {'width': 18.75, 'height': 15},
        'large': {'width': 18.75, 'height': 30}
    },
    'sections': {
        'top': 5,
        'upper': 20,
        'bottom': 70
    },
    'fonts': {
        'title': {'size': int(FONT_SIZE_TITLE * CURRENT_MONITOR['font_scale']), 'color': COLOR_FONT_TITLE},
        'subtitle': {'size': int(FONT_SIZE_SUBTITLE * CURRENT_MONITOR['font_scale']), 'color': COLOR_FONT_SUBTITLE},
        'body': {'size': int(FONT_SIZE_BODY * CURRENT_MONITOR['font_scale']), 'color': COLOR_FONT_BODY},
        'small': {'size': int(FONT_SIZE_SMALL * CURRENT_MONITOR['font_scale']), 'color': COLOR_FONT_SMALL}
    },
    'backgrounds': {
        'title': {'color': COLOR_BLACK, 'alpha': 180},
        'content': {'color': COLOR_BLACK, 'alpha': 120}
    }
}

#########################################
# ZONE-BASED LAYOUT (V2 - Mirror Optimized)
#########################################

LAYOUT_V2 = {
    'zones': {
        'top_bar': {'y': 0, 'height': 95},
        'bottom_bar': {'height': 40},
        'left_column': {'x': 0, 'width_pct': 0.22},
        'right_column': {'width_pct': 0.22},
        'center': {'width_pct': 0.56},
    },
    'left_modules': ['weather', 'calendar', 'countdown', 'smarthome', 'octopus_energy'],
    'right_modules': ['greeting', 'phone', 'quote', 'news', 'fitbit', 'openclaw', 'sysinfo'],
    'top_bar_modules': ['clock'],
    'bottom_bar_modules': ['stocks'],
    'center_overlay_modules': ['avatar', 'ai_interaction', 'ai_voice', 'eleven_voice'],
    'fullscreen_overlay_modules': ['retro_characters'],
    'module_gap': 15,
    'edge_padding': 15,
}

#########################################
# ANIMATION SETTINGS
#########################################

ANIMATION = {
    'fade_duration_ms': 400,
    'state_transition_ms': 800,
    'headline_fade_ms': 300,
    'notification_display_ms': 5000,
    'notification_fade_ms': 500,
    'scroll_speed_clock': 0.5,
    'scroll_speed_ticker': 1.0,
    'pulse_speed_alert': 2.0,
}

#########################################
# MAIN CONFIGURATION
#########################################

def draw_module_background_fallback(screen, x, y, module_width, module_height, padding=10):
    """No-op: mirror UI has no module backgrounds (black = transparent)."""
    pass

CONFIG = {
    'screen': {
        'fullscreen': True,
        'size': (SCREEN_WIDTH_DEFAULT, SCREEN_HEIGHT_DEFAULT),
        'scale': 1.0
    },
    'layout': LAYOUT,
    'update_schedule': {
        'time': time(5, 30),
        'frequency': 'daily'
    },
    'frame_rate': 30,
    
    # Module configurations
    'clock': {
        'class': 'ClockModule',
        'params': {
            'time_font_size': FONT_SIZE_CLOCK,
            'date_font_size': FONT_SIZE_BODY,
            'color': COLOR_TEXT_PRIMARY,
            'time_format': '%H:%M:%S',
            'date_format': '%A, %B %d, %Y',
            'timezone': 'local',
            'scrolling': True
        }
    },
    'weather': {
        'class': 'WeatherModule',
        'params': {
            'api_key': os.getenv('OPENWEATHERMAP_API_KEY'),
            'city': 'Birmingham,UK',
            'screen_width': CURRENT_MONITOR['resolution'][0],
            'screen_height': CURRENT_MONITOR['resolution'][1],
            'icons_path': weather_icons_path
        }
    },
    'stocks': {
        'class': 'StocksModule',
        'params': {
            'tickers': ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'NVDA', 'AMD', 'RR.L', 'LLOY.L'],
            'alpha_vantage_key': os.getenv('ALPHA_VANTAGE_KEY', ''),
        }
    },
    'calendar': {
        'class': 'CalendarModule',
        'params': {
            'config': {
                'client_id': os.getenv('GOOGLE_CLIENT_ID'),
                'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
                'access_token': os.getenv('GOOGLE_ACCESS_TOKEN'),
                'refresh_token': os.getenv('GOOGLE_REFRESH_TOKEN')
            }
        }
    },
    'fitbit': {
        'class': 'FitbitModule',
        'params': {
            'config': {
                'client_id': os.getenv('FITBIT_CLIENT_ID'),
                'client_secret': os.getenv('FITBIT_CLIENT_SECRET'),
                'access_token': os.getenv('FITBIT_ACCESS_TOKEN'),
                'refresh_token': os.getenv('FITBIT_REFRESH_TOKEN'),
            },
            'update_schedule': {'time': time(5, 30)}
        }
    },
    'retro_characters': {
        'class': 'RetroCharactersModule',
        'params': {
            'screen_size': CURRENT_MONITOR['resolution'],
            'icon_size': 64,
            'icon_directory': retro_icons_path,
            # Drip feed: slow spawn rate, gentle fall, and a high cap so it
            # never blocks (a low cap caused fill-then-refill batches). More
            # on screen comes from the slower fall (longer dwell), not a
            # faster spawn, so appearances stay spread out (~1.2s apart).
            'spawn_probability': 0.028,
            'fall_speed': 2.0,
            'max_active_icons': 60,
            'rotation_speed': 1
        }
    },
    'ai_voice': {
        'class': 'AIVoiceModule',
        'params': {
            'openai': {
                'api_key': None,  # Fetched from env in module
                # gpt-realtime-mini: best cost/latency for casual chat.
                # Switch to 'gpt-realtime-2' for reasoning-class replies.
                'model': 'gpt-realtime-mini',
                'voice': 'marin',
            },
            'audio': {
                'device_index': 2,
                # plughw (not hw) so ALSA resamples the USB mic to the
                # Realtime API's 24 kHz. Card number is hardware-specific.
                'alsa_device': 'plughw:3,0',
                # End a live conversation after this many idle seconds
                'conversation_timeout': 25,
                # Hard cap on any single conversation, idle or not
                'max_conversation_seconds': 180,
            },
            'debug_write': False,
        }
    },
    'avatar': {
        'class': 'AvatarModule',
        'params': {
            'size': 420,
            'transparency': 205,  # semi-transparent ghost-on-glass look
            'scanlines': True,    # faint CRT lines, Red Dwarf style
            # Face frames live in assets/avatar/ (see README.txt there)
        }
    },
    'ai_interaction': {
        'class': 'AIInteractionModule',
        'params': {
            'openai': {
                'api_key': None,  # Fetched from env in module
                'model': 'gpt-5.4-mini'
            },
            'audio': {
                'device_index': 2,
                'mic_energy_threshold': 500,
                'tts_volume': 0.8,
                'wav_volume': 0.5
            },
            'use_direct_audio': True,
            'disable_audio': False
        }
    },
    'eleven_voice': {
        'class': 'ElevenVoice',
        'params': {
            'api_key': os.getenv('ELEVENLABS_API_KEY', 'your-eleven-api-key'),
            'voice_id': os.getenv('ELEVENLABS_VOICE_ID', 'your-voice-id'),
            'openai_key': os.getenv('OPENAI_API_KEY', 'your-openai-api-key')
        }
    },
    'countdown': {
        'class': 'CountdownModule',
        'params': {
            'events': [
                {'name': 'Christmas', 'date': '2026-12-25'},
                {'name': 'New Year', 'date': '2027-01-01'},
            ]
        }
    },
    'quote': {
        'class': 'QuoteModule',
        'params': {}
    },
    'news': {
        'class': 'NewsModule',
        'params': {
            'feeds': [
                {'name': 'BBC', 'url': 'http://feeds.bbci.co.uk/news/rss.xml'},
                {'name': 'Guardian', 'url': 'https://www.theguardian.com/uk/rss'},
            ],
            'rotation_interval': 15,
            'max_headlines': 8
        }
    },
    'openclaw': {
        'class': 'OpenClawModule',
        'params': {
            'gateway_url': os.getenv('OPENCLAW_GATEWAY_URL', ''),
            'token': os.getenv('OPENCLAW_GATEWAY_TOKEN', ''),
            'device_id': 'ai-mirror-pi5',
            'notification_timeout': 10,
            'max_inbox_messages': 5,
            'voice_reply_enabled': True
        }
    },

    'smarthome': {
        'class': 'SmartHomeModule',
        'params': {
            # Accept both env spellings; some Variables.env copies used the
            # long HOME_ASSISTANT_* names
            'ha_url': os.getenv('HA_URL') or os.getenv('HOME_ASSISTANT_URL', ''),
            'ha_token': os.getenv('HA_TOKEN') or os.getenv('HOME_ASSISTANT_ACCESS_TOKEN', ''),
            # Curate exactly which entities show by setting HA_ENTITIES in
            # Variables.env (comma-separated entity ids). Empty = auto-discover.
            'entities': [e.strip() for e in os.getenv('HA_ENTITIES', '').split(',') if e.strip()],
            'update_interval_minutes': 2,
            'max_entities': 20,      # discovered total (dashboard shows all)
            'mini_entities': 8,      # shown in the left-column mini view
            'dashboard_timeout': 60,  # seconds before dashboard auto-closes
        }
    },
    'sysinfo': {
        'class': 'SysInfoModule',
        'params': {
            'update_interval_seconds': 10,
        }
    },
    'phone': {
        'class': 'PhoneModule',
        'params': {
            'ha_url': os.getenv('HA_URL') or os.getenv('HOME_ASSISTANT_URL', ''),
            'ha_token': os.getenv('HA_TOKEN') or os.getenv('HOME_ASSISTANT_ACCESS_TOKEN', ''),
            'battery_entity': '',     # auto-discovers the iPhone battery sensor
            'travel_minutes': 25,     # commute buffer for the Leave countdown
            'lead_window_minutes': 180,
            'update_interval_minutes': 5,
        }
    },
    'greeting': {
        'class': 'GreetingModule',
        'params': {
            'rotation_interval': 60,
        }
    },
    'octopus_energy': {
        'class': 'OctopusEnergyModule',
        'params': {
            'api_key': os.getenv('OCTOPUS_API_KEY', ''),
            'account_number': os.getenv('OCTOPUS_ACCOUNT_NUMBER', ''),
        }
    },

    # Phone control panel served on the LAN (http://<pi-ip>:8780)
    'web_panel': {
        'enabled': True,
        'port': 8780,
    },

    # Audio and sound effects
    'sound_effects_path': sound_effects_path,
    'audio': {
        'mic_energy_threshold': 500,
        'tts_volume': 0.8,
        'wav_volume': 0.5
    },
    
    # Module visibility settings
    'module_visibility': {
        'clock': True,
        'weather': True,
        'stocks': True,
        'calendar': True,
        'fitbit': True,
        'retro_characters': True,
        'ai_voice': False,
        'ai_interaction': False,
        'avatar': True,  # Only draws while a voice conversation is active
        'countdown': True,
        'quote': True,
        'news': True,
        'openclaw': True,
        'smarthome': True,
        'sysinfo': True,
        'greeting': True,
        'octopus_energy': True,
        'phone': True
    },
    
    # Keyboard toggles: keys 1-9, 0 map to these modules (in order)
    'toggle_modules': [
        'weather', 'calendar', 'countdown', 'smarthome',
        'greeting', 'quote', 'news', 'fitbit',
        'openclaw', 'sysinfo',
    ],

    # State-specific module settings
    'screensaver_modules': ['retro_characters'],
    'sleep_modules': ['clock'],
    
    # Debug settings
    'debug': {
        'enabled': True,
        'log_level': 'INFO'
    },
    
    # Visual effects settings
    'visual_effects': {
        'enabled': True,
        'animation_speed': 1.0,
        'transparency': {
            'background': 180,
            'text': 220,
            'highlights': 255
        }
    },
    
    # Screen settings
    'current_monitor': {
        'width': CURRENT_MONITOR['resolution'][0],
        'height': CURRENT_MONITOR['resolution'][1],
        'is_portrait': True,
    },
    
    # Module styling
    'module_styling': {
        'font_family': FONT_NAME,
        'fonts': {
            'title': {'size': FONT_SIZE_TITLE, 'color': COLOR_TEXT_DIM},
            'subtitle': {'size': FONT_SIZE_SUBTITLE, 'color': COLOR_TEXT_SECONDARY},
            'body': {'size': FONT_SIZE_BODY, 'color': COLOR_TEXT_PRIMARY},
            'small': {'size': FONT_SIZE_SMALL, 'color': COLOR_TEXT_SECONDARY}
        },
        'backgrounds': {
            'module': None,
            'header': None,
            'highlight': None
        },
        'separator_color': COLOR_SEPARATOR,
        'spacing': {
            'line_height': DEFAULT_LINE_HEIGHT,
            'padding': DEFAULT_PADDING
        },
        'radius': DEFAULT_RADIUS,
        'module_dimensions': {
            'standard': {'width': 300, 'height': 250, 'header_height': 0},
            'large': {'width': 300, 'height': 500, 'header_height': 0}
        }
    },

    # Layout V2 and animation references
    'layout_v2': LAYOUT_V2,
    'animation': ANIMATION
}