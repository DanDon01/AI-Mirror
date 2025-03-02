from dotenv import load_dotenv
import os
from datetime import time
import pygame

# Get the directory of the current file (config.py)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the path to Variables.env in the parent directory
env_path = os.path.join(current_dir, '..', 'Variables.env')

# Load the .env file
load_dotenv(env_path)

# Initialize pygame to access font information
pygame.font.init()

# Font settings
FONT_NAME = "Helvetica"
FONT_SIZE = 18
LINE_SPACING = 25  # Add this line for consistent line spacing

# Color settings
COLOR_FONT_DEFAULT = (200, 200, 200)  # Light grey
COLOR_PASTEL_GREEN = (152, 251, 152)  # Pale green
COLOR_PASTEL_RED = (255, 162, 173)    # Light pink (as a pastel red)
COLOR_PASTEL_BLUE = (173, 216, 230)   # Light blue

# Transparency setting (0 is fully transparent, 255 is fully opaque)
TRANSPARENCY = 215

# Construct paths for asset directories
assets_dir = os.path.join(current_dir, 'assets')
retro_icons_path = os.path.join(assets_dir, 'retro_icons')
weather_icons_path = os.path.join(assets_dir, 'weather_icons')
sound_effects_path = os.path.join(assets_dir, 'sound_effects')  # Changed from 'sound-effects' to 'sound_effects'

# Screen Layout Configuration
SCREEN_PADDING = 20  # Padding from screen edges
MODULE_SPACING = 10  # Spacing between modules

# Screen configurations for different monitor sizes
MONITOR_CONFIGS = {
    '27_portrait': {
        'resolution': (1440, 2560),  # 27" 1440p monitor in portrait
        'module_scale': 1.0,         # Base scale
        'font_scale': 1.0           # Base font scale
    },
    '24_portrait': {
        'resolution': (1200, 1920),  # 24" 1200p monitor in portrait
        'module_scale': 0.833,       # Scale factor relative to 27"
        'font_scale': 0.9           # Slightly smaller fonts
    },
    '21_portrait': {
        'resolution': (768, 1024),   # 21" monitor in portrait
        'module_scale': 0.533,       # Scale factor relative to 27"
        'font_scale': 0.8           # Even smaller fonts
    }
}

# Default to 27" portrait monitor
CURRENT_MONITOR = MONITOR_CONFIGS['27_portrait']

# Update LAYOUT with monitor-specific scaling
LAYOUT = {
    # Screen and general layout
    'screen_padding': int(30 * CURRENT_MONITOR['module_scale']),
    'module_spacing': int(15 * CURRENT_MONITOR['module_scale']),
    
    # Module dimensions (as percentage of screen)
    'module_sizes': {
        'standard': {
            'width': 25,   # percent of screen width
            'height': 15   # percent of screen height
        },
        'large': {
            'width': 25,
            'height': 30
        }
    },
    
    # Module positions (as percentage of screen height)
    'sections': {
        'top': 5,      # Clock
        'upper': 20,   # Weather & Stocks
        'bottom': 70   # Calendar & Fitbit
    },
    
    # Visual styling with monitor-specific font scaling
    'fonts': {
        'title': {
            'size': int(36 * CURRENT_MONITOR['font_scale']),
            'color': (255, 255, 255)
        },
        'subtitle': {
            'size': int(28 * CURRENT_MONITOR['font_scale']),
            'color': (200, 200, 200)
        },
        'body': {
            'size': int(24 * CURRENT_MONITOR['font_scale']),
            'color': (180, 180, 180)
        },
        'small': {
            'size': int(18 * CURRENT_MONITOR['font_scale']),
            'color': (160, 160, 160)
        }
    },
    
    # Module backgrounds
    'backgrounds': {
        'title': {
            'color': (0, 0, 0),
            'alpha': 180
        },
        'content': {
            'color': (0, 0, 0),
            'alpha': 120
        }
    }
}

CONFIG = {
    'screen': {
        'fullscreen': True,
        'size': (800, 480),  # Fallback size if current_monitor not set
        'scale': 1.0
    },
    'layout': LAYOUT,
    'update_schedule': {
        'time': time(5, 30),  # Update at 5:30 AM
        'frequency': 'daily'
    },
    'frame_rate': 30,
    'fitbit': {
        'class': 'FitbitModule',
        'params': {
            'config': {
                'client_id': os.getenv('FITBIT_CLIENT_ID'),
                'client_secret': os.getenv('FITBIT_CLIENT_SECRET'),
                'access_token': os.getenv('FITBIT_ACCESS_TOKEN'),
                'refresh_token': os.getenv('FITBIT_REFRESH_TOKEN'),
            },
            'update_schedule': {
                'time': time(5, 30)  # Update at 5:30 AM
            }
        }
    },  
    'stocks': {
       'class': 'StocksModule',
       'params': {
            'tickers': ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'NVDA', 'AMD', 'RR.L', 'LLOY.L']
       }
    },
    'weather': {
        'class': 'WeatherModule',
        'params': {
            'api_key': os.getenv('OPENWEATHERMAP_API_KEY'),
            'city': 'Birmingham,UK',
            'screen_width': 768,
            'screen_height': 1024,
            'icons_path': weather_icons_path  # This line should match the parameter name in WeatherModule.__init__
        }
    },
    'calendar': {
        'class': 'CalendarModule',  # Added Calendar module class
        'params': {
            'config': {
                'client_id': os.getenv('GOOGLE_CLIENT_ID'),
                'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
                'access_token': os.getenv('GOOGLE_ACCESS_TOKEN'),
                'refresh_token': os.getenv('GOOGLE_REFRESH_TOKEN')
            }
        }
    },
    'clock': {
        'class': 'ClockModule',
        'params': {
            'time_font_size': 24,
            'date_font_size': 12,
            'color': COLOR_FONT_DEFAULT,  # Make sure this color is defined in your config
            'time_format': '%H:%M:%S',
            'date_format': '%A, %B %d, %Y',
            'timezone': 'local'  # Or specify a timezone like 'Europe/London'
        }
    },
    'retro_characters': {
        'class': 'RetroCharactersModule',
        'params': {
            'screen_size': (768, 1024),
            'icon_size': 64,
            'icon_directory': retro_icons_path,
            'spawn_probability': 0.002,  # Increased for more frequent icons
            'fall_speed': 1,
            'max_active_icons': 20,  # Increased for more icons on screen
            'rotation_speed': 1
        }
    },
    'ai_interaction': {
        'class': 'AIInteractionModule',
        'params': {
            'config': {
                'disable_audio': False,
                'openai': {
                    'api_key': os.getenv('OPENAI_API_KEY'),
                    'model': 'gpt-4-1106-preview'
                },
                'audio': {
                    'mic_energy_threshold': 500,
                    'tts_volume': 0.8,
                    'wav_volume': 0.5
                }
            }
        }
    },
    'sound_effects_path': sound_effects_path,  # Add this line
    'audio': {
        'mic_energy_threshold': 500,  # Adjust this value to increase/decrease mic sensitivity
        'tts_volume': 0.8,  # Adjust this value between 0.0 and 1.0 for TTS volume
        'wav_volume': 0.5,  # Adjust this value between 0.0 and 1.0 for WAV file volume
    },
    'module_visibility': {
        'clock': True,
        'weather': True,
        'stocks': True,
        'calendar': True,
        'fitbit': True,
        'retro_characters': True,
        'ai_interaction': {
            'params': {
                'config': {
                    'disable_audio': True,  # Set to True to completely disable audio (prevents crashes)
                    # ... other settings
                }
            }
        }
    },
    'debug': {
        'enabled': False,  # Set to True when you need detailed logging
        'log_level': 'INFO'  # Can be 'DEBUG', 'INFO', 'WARNING', 'ERROR'
    },
    'screensaver_modules': ['retro_characters'],
    'sleep_modules': ['clock'],
    'visual_effects': {
        'enabled': True,
        'animation_speed': 1.0,  # Adjust to speed up or slow down animations
        'transparency': {
            'background': 180,
            'text': 220,
            'highlights': 255
        }
    },
    'current_monitor': {
        'width': 800,  # Set to actual physical width of your display 
        'height': 480,  # Set to actual physical height of your display
        'is_portrait': False  # Set to False since the Pi should use landscape mode
    },
    'module_styling': {
        'font_family': FONT_NAME,
        'fonts': {
            'title': {
                'size': 24,
                'color': (240, 240, 240)  # Slightly off-white for titles
            },
            'subtitle': {
                'size': 20,
                'color': (220, 220, 220)
            },
            'body': {
                'size': 16,
                'color': (200, 200, 200)
            },
            'small': {
                'size': 14,
                'color': (180, 180, 180)
            }
        },
        'backgrounds': {
            'module': (20, 20, 20),       # Almost black
            'header': (40, 40, 40),       # Dark gray
            'highlight': (30, 30, 40)     # Slightly bluish dark background
        },
        'spacing': {
            'line_height': 22,            # Default line spacing
            'padding': 10                 # Default padding
        },
        'radius': 15                      # Default corner radius
    },
}