import fitbit
from datetime import datetime, timedelta, time
import pygame
import logging
from config import CONFIG
import os
from pathlib import Path
import requests
import base64

class FitbitModule:
    def __init__(self, config):
        self.client_id = config['client_id']
        self.client_secret = config['client_secret']
        self.access_token = config['access_token']
        self.refresh_token = config['refresh_token']
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
        self.update_interval = config.get('update_interval', 300)  # 5 minutes default
        self.retry_after = 0
        logging.info(f"Initializing FitbitModule with client_id: {self.client_id}")

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

    def should_update(self):
        now = time.time()
        if now < self.retry_after:
            return False
        return self.last_update is None or (datetime.now() - self.last_update).total_seconds() >= self.update_interval

    def update(self):
        if not self.should_update():
            return

        try:
            if not self.client:
                self.initialize_client()
                if not self.client:
                    return

            today = datetime.now().strftime("%Y-%m-%d")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            # Fetch activity data
            daily_data = self.client.activities(date=today)['summary']
            self.data['steps'] = daily_data['steps']
            self.data['calories'] = daily_data['caloriesOut']
            self.data['active_minutes'] = daily_data['fairlyActiveMinutes'] + daily_data['veryActiveMinutes']

            # Fetch heart rate data
            heart_data = self.client.heart(date=today)['activities-heart']
            self.data['resting_heart_rate'] = heart_data[0]['value'].get('restingHeartRate', 'N/A')

            # Fetch sleep data
            sleep_data = self.client.sleep(date=yesterday)
            if 'summary' in sleep_data:
                total_minutes_asleep = sleep_data['summary'].get('totalMinutesAsleep', 0)
                hours, minutes = divmod(total_minutes_asleep, 60)
                self.data['sleep'] = f"{hours:02}:{minutes:02}"
            else:
                self.data['sleep'] = 'N/A'

            self.last_update = datetime.now()
            logging.info("Fitbit data updated successfully")
            logging.debug(f"Updated Fitbit data: {self.data}")

        except fitbit.exceptions.HTTPTooManyRequests as e:
            retry_after = int(e.retry_after_secs)
            self.retry_after = time.time() + retry_after
            logging.warning(f"Rate limited. Retrying after {retry_after} seconds.")
        except fitbit.exceptions.HTTPUnauthorized:
            logging.warning("Access token expired, refreshing token")
            self.refresh_access_token()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching Fitbit data: {e}")
            if hasattr(e, 'response') and e.response:
                logging.error(f"Response status code: {e.response.status_code}")
                logging.error(f"Response content: {e.response.text}")
        except Exception as e:
            logging.error(f"Unexpected error updating Fitbit data: {e}")

    def refresh_access_token(self):
        try:
            token_url = "https://api.fitbit.com/oauth2/token"
            response = requests.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                },
                auth=(self.client_id, self.client_secret)
            )
            new_tokens = response.json()
            
            if 'access_token' in new_tokens and 'refresh_token' in new_tokens:
                self.access_token = new_tokens['access_token']
                self.refresh_token = new_tokens['refresh_token']
                self.initialize_client()
                self.save_tokens(new_tokens)
                logging.info("Access token refreshed successfully")
            else:
                logging.error(f"Error refreshing token: {new_tokens.get('errors', 'Unknown error')}")
        except Exception as e:
            logging.error(f"Error refreshing access token: {e}")

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