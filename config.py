from dotenv import load_dotenv
import os
from datetime import time

# Get the directory of the current file (config.py)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the path to Variables.env in the parent directory
env_path = os.path.join(current_dir, '..', 'Variables.env')

# Load the .env file
load_dotenv(env_path)

CONFIG = {
    'screen': {
        'size': (1080, 1920)  # Portrait mode 21-inch monitor
    },
    'update_schedule': {
        'time': time(5, 30),  # Update at 5:30 AM
        'frequency': 'daily'
    },
    'frame_rate': 30,
    'fitbit': {
        'class': 'FitbitModule',
        'params': {
            'client_id': os.getenv('FITBIT_CLIENT_ID'),
            'client_secret': os.getenv('FITBIT_CLIENT_SECRET'),
            'access_token': os.getenv('FITBIT_ACCESS_TOKEN'),
            'refresh_token': os.getenv('FITBIT_REFRESH_TOKEN'),
            'update_schedule': {
                'time': time(5, 30)  # Update at 5:30 AM
            }
        }
    },  
    'stocks': {
        'tickers': ['AAPL', 'GOOGL', 'MSFT']  # Add your preferred stock tickers
    },
    'weather': {
        'class': 'WeatherModule',
        'params': {
            'api_key': os.getenv('OPENWEATHERMAP_API_KEY'),
            'city': 'Birmingham'  # Replace with your actual city name
        }
    },
    'calendar': {
        'class': 'CalendarModule',  # Added Calendar module class
        'params': {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'access_token': os.getenv('GOOGLE_ACCESS_TOKEN'),
            'refresh_token': os.getenv('GOOGLE_REFRESH_TOKEN')
        }
    },
    'smart_home': {
        'class': 'SmartHomeModule',
        'params': {
            'ha_url': os.getenv('HOME_ASSISTANT_URL'),
            'access_token': os.getenv('HOME_ASSISTANT_ACCESS_TOKEN'),
            'entities': [
                'sensor.living_room_temperature',
                'sensor.living_room_humidity',
                'sensor.bedroom_temperature',
                'sensor.bedroom_humidity'
            ]
        },
        'font_size': 24,
        'color': (255, 255, 255),  # White
        'retry_attempts': 3
    },
    'clock': {
        'font_file': None,  # Use None for system default
        'font_size': 60,
        'color': (255, 255, 255),  # White
        'time_format': '%H:%M:%S',
        'date_format': '%A, %B %d, %Y',
        'timezone': 'local'  # Or specify a timezone like 'US/Pacific'
    },
    'positions': {
        'clock': (20, 20),  # Top-left corner
        'weather': (20, 240),  # Below clock in top-left
        'fitbit': (20, 1620),  # Bottom-left corner
        'smart_home': (20, 1400),  # Above fitbit in bottom-left
        'calendar': (540, 20),  # Top-right corner
        'stocks': (540, 1620),  # Bottom-right corner
    }
}