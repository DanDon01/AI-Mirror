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
COLOR_PASTEL_RED = (255, 182, 193)    # Light pink (as a pastel red)
COLOR_PASTEL_BLUE = (173, 216, 230)   # Light blue

# Transparency setting (0 is fully transparent, 255 is fully opaque)
TRANSPARENCY = 215

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
            'tickers': ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'NVDA', 'AMD', 'RR.L', 'LLOY.L', 'BAE.L']
       }
    },

    'weather': {
        'class': 'WeatherModule',
        'params': {
            'api_key': os.getenv('OPENWEATHERMAP_API_KEY'),
            'city': 'Birmingham',
            'screen_width': 768,  # Match your screen width
            'screen_height': 1024  # Match your screen height
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
        'clock': (20, 20),  # Top-left corner
        'weather': (20, 100),  # Below clock in top-left
        'fitbit': (20, 300),  # Bottom-left corner
        'smart_home': (20, 0),  # Above fitbit in bottom-left
        'calendar': (20, 450),  # Top-right corner
        'stocks': (550, 120),  # Bottom-right corner
    }
}