import fitbit
from datetime import datetime, timedelta, time
import pygame
import logging
from config import CONFIG
import os
from pathlib import Path
import requests
import base64
import traceback

class FitbitModule:
    def __init__(self, config):
        logging.info("Initializing FitbitModule")
        self.config = config
        self.client_id = config['client_id']
        self.client_secret = config['client_secret']
        self.access_token = config['access_token']
        self.refresh_token = config['refresh_token']
        self.update_time = config.get('update_schedule', {}).get('time', time(0, 0))
        self.client = None
        self.initialize_client()
        self.data = {
            'steps': 'N/A',
            'calories': 'N/A',
            'active_minutes': 'N/A',
            'sleep': 'N/A',
            'resting_heart_rate': 'N/A'
        }
        self.last_update = None
        self.last_api_call = 0
        self.api_call_count = 0
        self.backoff_time = 1  # Start with 1 second backoff

    def initialize_client(self):
        try:
            self.client = fitbit.Fitbit(
                self.client_id,
                self.client_secret,
                access_token=self.access_token,
                refresh_token=self.refresh_token,
                system='en_US'
            )
            logging.info("Fitbit client initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing Fitbit client: {e}")
            logging.error(traceback.format_exc())

    def update(self):
        if not self.should_update():
            return

        try:
            self.rate_limit_api_call()
            
            today = datetime.now().strftime("%Y-%m-%d")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            # Fetch activity data
            daily_data = self.make_api_call(self.client.activities, date=today)['summary']
            self.data['steps'] = daily_data.get('steps', 'N/A')
            self.data['calories'] = daily_data.get('caloriesOut', 'N/A')
            self.data['active_minutes'] = daily_data.get('fairlyActiveMinutes', 0) + daily_data.get('veryActiveMinutes', 0)

            # Fetch heart rate data
            try:
                heart_data = self.make_api_call(self.client.intraday_time_series, resource='activities/heart', base_date=today, detail_level='1d')
                self.data['resting_heart_rate'] = heart_data['activities-heart'][0]['value'].get('restingHeartRate', 'N/A')
            except Exception as e:
                logging.error(f"Error fetching heart rate data: {e}")
                self.data['resting_heart_rate'] = 'N/A'

            # Fetch sleep data
            try:
                sleep_data = self.make_api_call(self.client.sleep, date=yesterday)
                if 'summary' in sleep_data and 'totalMinutesAsleep' in sleep_data['summary']:
                    total_minutes_asleep = sleep_data['summary']['totalMinutesAsleep']
                    hours, minutes = divmod(total_minutes_asleep, 60)
                    self.data['sleep'] = f"{hours:02}:{minutes:02}"
                else:
                    self.data['sleep'] = 'N/A'
            except Exception as e:
                logging.error(f"Error fetching sleep data: {e}")
                self.data['sleep'] = 'N/A'

            self.last_update = datetime.now()
            logging.info("Fitbit data updated successfully")
            logging.debug(f"Updated Fitbit data: {self.data}")

        except fitbit.exceptions.HTTPTooManyRequests as e:
            logging.warning(f"Rate limited. Retrying after {e.retry_after_secs} seconds.")
            self.backoff_time = max(self.backoff_time * 2, e.retry_after_secs)
        except fitbit.exceptions.HTTPUnauthorized:
            logging.warning("Access token expired, refreshing token")
            self.refresh_access_token()
        except Exception as e:
            logging.error(f"Unexpected error updating Fitbit data: {e}")
            logging.error(traceback.format_exc())

    def should_update(self):
        now = datetime.now()
        if self.last_update is None:
            return True
        time_since_last_update = now - self.last_update
        return time_since_last_update.total_seconds() >= 3600  # Update every hour

    def rate_limit_api_call(self):
        current_time = time.time()
        if current_time - self.last_api_call < 1:  # Ensure at least 1 second between calls
            time.sleep(1 - (current_time - self.last_api_call))
        self.last_api_call = time.time()
        self.api_call_count += 1
        if self.api_call_count > 150:  # Fitbit's rate limit is 150 calls per hour
            time.sleep(self.backoff_time)
            self.backoff_time *= 2  # Exponential backoff
            if self.backoff_time > 3600:  # Cap at 1 hour
                self.backoff_time = 3600
            self.api_call_count = 0

    def make_api_call(self, func, **kwargs):
        self.rate_limit_api_call()
        return func(**kwargs)

    def refresh_access_token(self):
        try:
            token = self.client.client.refresh_token()
            self.access_token = token['access_token']
            self.refresh_token = token['refresh_token']
            self.initialize_client()
            self.save_tokens(token)
            logging.info("Access token refreshed successfully")
        except Exception as e:
            logging.error(f"Error refreshing access token: {e}")
            logging.error(traceback.format_exc())

    def save_tokens(self, tokens):
        try:
            current_dir = Path(__file__).parent
            env_file_path = current_dir.parent / 'Variables.env'

            with open(env_file_path, 'r') as file:
                lines = file.readlines()

            for i, line in enumerate(lines):
                if line.startswith('FITBIT_ACCESS_TOKEN='):
                    lines[i] = f"FITBIT_ACCESS_TOKEN={tokens['access_token']}\n"
                elif line.startswith('FITBIT_REFRESH_TOKEN='):
                    lines[i] = f"FITBIT_REFRESH_TOKEN={tokens['refresh_token']}\n"

            with open(env_file_path, 'w') as file:
                file.writelines(lines)

            logging.info("Tokens updated in Variables.env")
        except Exception as e:
            logging.error(f"Error saving tokens to Variables.env: {e}")

    def draw(self, screen, position):
        font = pygame.font.Font(None, 36)
        x, y = position
        for i, (key, value) in enumerate(self.data.items()):
            text = f"{key.replace('_', ' ').title()}: {value}"
            text_surface = font.render(text, True, (255, 255, 255))
            screen.blit(text_surface, (x, y + i * 40))

    def cleanup(self):
        pass