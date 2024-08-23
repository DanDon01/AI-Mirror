from dotenv import load_dotenv
import os

load_dotenv()  # Load variables from .env file

CONFIG = {
    'screen': {
        'size': (800, 480)  # Adjust as needed for your display
    },
    'update_intervals': {
        'fitbit': 300,  # 5 minutes
        'stocks': 900,  # 15 minutes
        'weather': 1800,  # 30 minutes
        'calendar': 3600,  # 1 hour
        'smart_home': 60,  # 1 minute
        'clock': 60  # 1 minute
    },
    'frame_rate': 30,
    'fitbit': {
        'client_id': 'your_fitbit_client_id',
        'client_secret': 'your_fitbit_client_secret',
        'access_token': 'your_fitbit_access_token',
        'refresh_token': 'your_fitbit_refresh_token'
    },
    'stocks': {
        'tickers': ['AAPL', 'GOOGL', 'MSFT']  # Add your preferred stock tickers
    },
    'weather': {
        'api_key': 'your_openweathermap_api_key',
        'city': 'Your City'
    },
    'calendar': {
        'credentials_file': 'path/to/your/credentials.json',
        'token_file': 'path/to/your/token.pickle'
    },
    'smart_home': {
        'class': 'SmartHomeModule',
        'params': {
            'ha_url': 'http://your_home_assistant_ip:8123',
            'access_token': 'your_long_lived_access_token',
            'entities': [
                'sensor.living_room_temperature',
                'sensor.living_room_humidity',
                'sensor.bedroom_temperature',
                'sensor.bedroom_humidity'
            ]
        },
        'font_size': 24,
        'color': (255, 255, 255),  # White
        'update_interval_minutes': 1,
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
}
