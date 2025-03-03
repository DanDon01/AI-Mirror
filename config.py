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

# Color Constants
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_FONT_DEFAULT = (240, 240, 240)
COLOR_FONT_TITLE = (150, 150, 150)
COLOR_FONT_SUBTITLE = (220, 220, 220)
COLOR_FONT_BODY = (200, 200, 200)
COLOR_FONT_SMALL = (180, 180, 180)
COLOR_PASTEL_GREEN = (152, 251, 152)
COLOR_PASTEL_RED = (255, 162, 173)
COLOR_PASTEL_BLUE = (173, 216, 230)

# Background Colors
COLOR_BG_MODULE = (20, 20, 20)
COLOR_BG_HEADER = (40, 40, 40)
COLOR_BG_HIGHLIGHT = (30, 30, 40)
COLOR_BG_MODULE_ALPHA = (20, 20, 20, 0)
COLOR_BG_HEADER_ALPHA = (40, 40, 40, 0)

# Transparency setting
TRANSPARENCY = 215

# Font Settings
FONT_NAME = "Helvetica"
FONT_SIZE_TITLE = 18
FONT_SIZE_SUBTITLE = 16
FONT_SIZE_BODY = 14
FONT_SIZE_SMALL = 12
FONT_SIZE = FONT_SIZE_BODY

# Spacing and Dimensions
LINE_SPACING = 25
DEFAULT_PADDING = 10
DEFAULT_LINE_HEIGHT = 22
DEFAULT_RADIUS = 15

# Standard screen dimensions
SCREEN_WIDTH_DEFAULT = 800
SCREEN_HEIGHT_DEFAULT = 1280

# Paths for assets
assets_dir = os.path.join(current_dir, 'assets')
retro_icons_path = os.path.join(assets_dir, 'retro_icons')
weather_icons_path = os.path.join(assets_dir, 'weather_icons')
sound_effects_path = os.path.join(assets_dir, 'sound_effects')

#########################################
# MONITOR CONFIGURATIONS
#########################################

SCREEN_PADDING = 20
MODULE_SPACING = 10

MONITOR_CONFIGS = {
    '27_portrait': {
        'resolution': (1440, 2560),
        'module_scale': 1.0,
        'font_scale': 1.0
    },
    '24_portrait': {
        'resolution': (1200, 1920),
        'module_scale': 0.833,
        'font_scale': 0.9
    },
    '21_portrait': {
        'resolution': (768, 1024),
        'module_scale': 0.533,
        'font_scale': 0.8
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
# MAIN CONFIGURATION
#########################################

def draw_module_background_fallback(screen, x, y, module_width, module_height, padding=10):
    s = pygame.Surface((module_width, module_height), pygame.SRCALPHA)
    s.fill(COLOR_BG_MODULE_ALPHA)
    screen.blit(s, (x - padding, y - padding))
    s = pygame.Surface((module_width, 40), pygame.SRCALPHA)
    s.fill(COLOR_BG_HEADER_ALPHA)
    screen.blit(s, (x - padding, y - padding))

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
            'time_font_size': FONT_SIZE_TITLE,
            'date_font_size': FONT_SIZE_SMALL,
            'color': COLOR_FONT_DEFAULT,
            'time_format': '%H:%M:%S',
            'date_format': '%A, %B %d, %Y',
            'timezone': 'local'
        }
    },
    'weather': {
        'class': 'WeatherModule',
        'params': {
            'api_key': os.getenv('OPENWEATHERMAP_API_KEY'),
            'city': 'Birmingham,UK',
            'screen_width': SCREEN_WIDTH_DEFAULT,
            'screen_height': SCREEN_HEIGHT_DEFAULT,
            'icons_path': weather_icons_path
        }
    },
    'stocks': {
        'class': 'StocksModule',
        'params': {
            'tickers': ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'NVDA', 'AMD', 'RR.L', 'LLOY.L']
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
            'screen_size': (SCREEN_WIDTH_DEFAULT, SCREEN_HEIGHT_DEFAULT),
            'icon_size': 64,
            'icon_directory': retro_icons_path,
            'spawn_probability': 0.002,
            'fall_speed': 1,
            'max_active_icons': 20,
            'rotation_speed': 1
        }
    },
    'ai_voice': {
        'class': 'AIVoiceModule',
        'params': {
            'openai': {
                'api_key': None,  # Fetched in module
                'model': None, # Fetched in module
            },
            'audio': {
                'device_index': 2
            }
        }
    },
    'ai_interaction': {
        'class': 'AIInteractionModule',
        'params': {
            'openai': {
                'api_key': None,  # Fetched in module
                'model': 'gpt-4o-mini'
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
        'ai_voice': True,
        'ai_interaction': True
    },
    
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
        'width': SCREEN_WIDTH_DEFAULT,
        'height': SCREEN_HEIGHT_DEFAULT,
        'is_portrait': False
    },
    
    # Module styling
    'module_styling': {
        'font_family': FONT_NAME,
        'fonts': {
            'title': {'size': FONT_SIZE_TITLE, 'color': COLOR_FONT_DEFAULT},
            'subtitle': {'size': FONT_SIZE_SUBTITLE, 'color': COLOR_FONT_SUBTITLE},
            'body': {'size': FONT_SIZE_BODY, 'color': COLOR_FONT_BODY},
            'small': {'size': FONT_SIZE_SMALL, 'color': COLOR_FONT_SMALL}
        },
        'backgrounds': {
            'module': COLOR_BG_MODULE,
            'header': COLOR_BG_HEADER,
            'highlight': COLOR_BG_HIGHLIGHT
        },
        'spacing': {
            'line_height': DEFAULT_LINE_HEIGHT,
            'padding': DEFAULT_PADDING
        },
        'radius': DEFAULT_RADIUS,
        'module_dimensions': {
            'standard': {'width': 225, 'height': 200, 'header_height': 40},
            'large': {'width': 225, 'height': 400, 'header_height': 40}
        }
    }
}