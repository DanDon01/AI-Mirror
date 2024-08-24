from dotenv import load_dotenv
import os
from datetime import time

load_dotenv('Variables.env')  # Load variables from Variables.env file

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
                'client_id': 'YOUR_FITBIT_CLIENT_ID',
                'client_secret': 'YOUR_FITBIT_CLIENT_SECRET',
                'access_token': 'YOUR_FITBIT_ACCESS_TOKEN',
                'refresh_token': 'YOUR_FITBIT_REFRESH_TOKEN',
                'update_interval': 5  # in minutes
    },
    'stocks': {
        'tickers': ['AAPL', 'GOOGL', 'MSFT']  # Add your preferred stock tickers
    },
    'weather': {
        'api_key': os.getenv('OPENWEATHERMAP_API_KEY'),
        'city': 'Your City'
    },
    'calendar': {
        'client_id': os.getenv('GOOGLE_CLIENT_ID'),
        'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
        'access_token': os.getenv('GOOGLE_ACCESS_TOKEN'),
        'refresh_token': os.getenv('GOOGLE_REFRESH_TOKEN')
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
        'weather': (10, 50),
        'fitbit': (10, 200),
        'stocks': (400, 50),
        'calendar': (400, 200),
        'smart_home': (10, 300)  # Added smart home position
    }
}}