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
        self.client = fitbit.Fitbit(
            self.client_id,
            self.client_secret,
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            system='en_US'
        )
        self.data = {
            'steps': 'N/A',
            'calories': 'N/A',
            'active_minutes': 'N/A',
            'sleep': 'N/A',
            'resting_heart_rate': 'N/A'
        }
        self.font = None
        self.last_update = None
        logging.info(f"Initializing FitbitModule with client_id: {self.client_id}")
        logging.info(f"access_token: {'set' if self.access_token else 'not set'}")
        logging.info(f"refresh_token: {'set' if self.refresh_token else 'not set'}")

    def should_update(self):
        now = datetime.now()
        scheduled_time = CONFIG['update_schedule']['time']
        if now.time() >= scheduled_time and (self.last_update is None or self.last_update.date() < now.date()):
            return True
        return False

    def update(self):
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            if self.should_update():
                    try:
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
                        sleep_url = f"https://api.fitbit.com/1.2/user/-/sleep/date/{yesterday}.json"
                        headers = {
                            "Authorization": f"Bearer {self.access_token}",
                            "Accept": "application/json"
                        }
                        response = requests.get(sleep_url, headers=headers)
                        response.raise_for_status()  # Raise an exception for bad responses
                        sleep_data = response.json()
                
                # Process sleep data
                        if 'summary' in sleep_data:
                            total_minutes_asleep = sleep_data['summary'].get('totalMinutesAsleep', 0)
                            total_time_in_bed = sleep_data['summary'].get('totalTimeInBed', 0)
                            hours_asleep, minutes_asleep = divmod(total_minutes_asleep, 60)
                            self.data['sleep'] = f"{hours_asleep:02}:{minutes_asleep:02}"
                            self.data['time_in_bed'] = f"{total_time_in_bed // 60:02}:{total_time_in_bed % 60:02}"
                    
                            if 'stages' in sleep_data['summary']:
                                stages = sleep_data['summary']['stages']
                                self.data['deep_sleep'] = stages.get('deep', 'N/A')
                                self.data['light_sleep'] = stages.get('light', 'N/A')
                                self.data['rem_sleep'] = stages.get('rem', 'N/A')
                                self.data['wake_sleep'] = stages.get('wake', 'N/A')
                        else:
                            logging.warning("Sleep summary data not found in the response")
                            self.data['sleep'] = 'N/A'
                            self.data['time_in_bed'] = 'N/A'

                        self.last_update = datetime.now()
                        logging.info("Fitbit data updated successfully")
                        logging.debug(f"Updated Fitbit data: {self.data}")
            
                    except requests.exceptions.RequestException as e:
                        logging.error(f"Error fetching sleep data: {e}")
                        self.data['sleep'] = 'N/A'
                        self.data['time_in_bed'] = 'N/A'
            
                    except fitbit.exceptions.HTTPUnauthorized:
                        logging.warning("Access token expired, refreshing token")
                        self.refresh_access_token()
                        self.update()  # Retry update after refreshing token
            
                    except Exception as e:
                        logging.error(f"Error fetching Fitbit data: {e}")
                        for key in self.data:
                            self.data[key] = 'N/A'
            else:
                break  # Exit if update is not needed

    def refresh_access_token(self):
        try:
            token_url = "https://api.fitbit.com/oauth2/token"
            auth_header = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            headers = {
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token
            }
            response = requests.post(token_url, headers=headers, data=data)
            new_tokens = response.json()
            
            if 'access_token' in new_tokens and 'refresh_token' in new_tokens:
                self.access_token = new_tokens['access_token']
                self.refresh_token = new_tokens['refresh_token']
                self.client = fitbit.Fitbit(
                    self.client_id,
                    self.client_secret,
                    access_token=self.access_token,
                    refresh_token=self.refresh_token,
                    system='en_US'
                )
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
        if self.font is None:
            self.font = pygame.font.Font(None, 36)

        try:
            x, y = position
            labels = [
                f"Steps: {self.data['steps']}",
                f"Calories: {self.data['calories']}",
                f"Active Minutes: {self.data['active_minutes']}",
                f"Sleep: {self.data['sleep']} mins",
                f"Resting Heart Rate: {self.data['resting_heart_rate']} bpm"
            ]
            for i, label in enumerate(labels):
                text_surface = self.font.render(label, True, (255, 255, 255))
                screen.blit(text_surface, (x, y + i * 40))
        except Exception as e:
            logging.error(f"Error drawing Fitbit data: {e}")
            error_surface = self.font.render("Fitbit data unavailable", True, (255, 0, 0))
            screen.blit(error_surface, position)

    def cleanup(self):
        pass