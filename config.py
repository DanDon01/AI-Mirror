CONFIG = {
    'screen': {
        'size': (800, 480)  # Adjust as needed for your display
    },
    'update_intervals': {
        'fitbit': 300,  # 5 minutes
        'stocks': 900,  # 15 minutes
        'weather': 1800,  # 30 minutes
        'calendar': 3600  # 1 hour
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
    'positions': {
        'time': (10, 10),
        'weather': (10, 50),
        'fitbit': (10, 200),
        'stocks': (400, 50),
        'calendar': (400, 200)
    }
}
