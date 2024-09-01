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
        'size': (800, 480)  # Adjust as needed for your display
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
            'city': 'Your City'
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
        'time': (10, 10),
        'clock': (10, 100),
        'fitbit': (10, 200),
        'weather': (10, 300),  # Positioned under Fitbit
        'calendar': (200, 200),  # Positioned next to Fitbit
        'stocks': (400, 50),
        'smart_home': (10, 400)  # Moved down to accommodate weather
    }
}