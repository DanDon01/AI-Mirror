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
weather_icons_path = os.path.join(assets_dir, 'weather_icons')  # Add this if you're using weather icons

CONFIG = {
    'screen': {
        'size': (768, 1024)  # Portrait mode 21-inch monitor
    },
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
       'class': 'StocksModule',  # Add this line to specify the class
       'params': {
            'tickers': ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'NVDA', 'AMD', 'RR.L', 'LLOY.L', ]
       }
    },
    'weather': {
        'class': 'WeatherModule',
        'params': {
            'api_key': os.getenv('OPENWEATHERMAP_API_KEY'),
            'city': 'Birmingham,UK',  # Specify the country code
            'screen_width': 768,  # Match your screen width
            'screen_height': 1024,  # Match your screen height
            'icons_path': weather_icons_path  # Add this if you're using weather icons
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
    'positions': {
        'clock': (5, 5),  # Position for the clock at the top of the screen
        'weather': (20, 100),  # Below clock in top-left
        'fitbit': (20, 280),  # Bottom-left corner
        'smart_home': (20, 0),  # Above fitbit in bottom-left
        'calendar': (20, 500),  # Top-right corner
        'stocks': (550, 140),  # Bottom-right corner
        'retro_characters': (0, 0),  # This module doesn't need a specific position as it covers the whole screen
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
            'screen_size': (768, 1024),  # Use the same size as your screen
            'icon_size': 64,
            'icon_directory': retro_icons_path,  # Use the absolute path
            'spawn_probability': 0.1,
            'fall_speed': 3,
            'max_active_icons': 10
        }
    }
}