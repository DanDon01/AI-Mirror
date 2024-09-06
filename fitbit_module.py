import fitbit
from datetime import datetime, timedelta
import time as time_module
import pygame
import logging
from config import CONFIG, FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, LINE_SPACING, TRANSPARENCY
import os
from pathlib import Path
import requests
import time
import traceback
from fitbit.api import Fitbit
from fitbit.exceptions import HTTPUnauthorized
from oauthlib.oauth2.rfc6749.errors import TokenExpiredError
import base64

class FitbitModule:
    def __init__(self, config, update_schedule):
        logging.info("Initializing FitbitModule")
        self.config = config
        self.client_id = config['client_id']
        self.client_secret = config['client_secret']
        self.access_token = config['access_token']
        self.refresh_token = config['refresh_token']
        self.update_time = update_schedule.get('time')
        logging.debug(f"Update time set to: {self.update_time}")
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
        self.font = None
        self.step_goal = 10000  # Set the step goal

    def initialize_client(self):
        try:
            self.client = fitbit.Fitbit(
                self.client_id,
                self.client_secret,
                oauth2=True,
                access_token=self.access_token,
                refresh_token=self.refresh_token,
                system='en_US'
            )
            logging.info("Fitbit client initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing Fitbit client: {e}")
            logging.error(traceback.format_exc())

    def update(self):
        logging.debug("Entering update method")
        if not self.should_update():
            logging.debug("Skipping Fitbit update: Not enough time has passed since last update")  # Changed to debug
            return

        try:
            self.rate_limit_api_call()
            
            today = datetime.now().strftime("%Y-%m-%d")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            logging.debug(f"Fetching data for today: {today}, yesterday: {yesterday}")

            # Fetch activity data
            daily_data = self.make_api_call(self.client.activities, date=today)['summary']
            self.data['steps'] = daily_data.get('steps', 'N/A')
            self.data['calories'] = daily_data.get('caloriesOut', 'N/A')
            self.data['active_minutes'] = daily_data.get('fairlyActiveMinutes', 0) + daily_data.get('veryActiveMinutes', 0)

            # Fetch heart rate data
            try:
                heart_data = self.make_api_call(self.client.intraday_time_series, resource='activities/heart', base_date=today, detail_level='1min')
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

        except Exception as e:
            logging.error(f"Error updating Fitbit data: {e}")
            logging.error(traceback.format_exc())

    def should_update(self):
        logging.debug("Checking if update is needed")
        now = datetime.now()
        logging.debug(f"Current time: {now}")
        logging.debug(f"Last update: {self.last_update}")
        if self.last_update is None:
            logging.debug("First update, should update")
            return True
        time_since_last_update = now - self.last_update
        should_update = time_since_last_update.total_seconds() >= 3600  # Update every hour
        logging.debug(f"Time since last update: {time_since_last_update.total_seconds()} seconds")
        logging.debug(f"Should update: {should_update}")
        return should_update

    def rate_limit_api_call(self):
        logging.debug("Entering rate_limit_api_call method")
        current_time = time_module.time()
        logging.debug(f"Current time: {current_time}")
        logging.debug(f"Last API call: {self.last_api_call}")
        if current_time - self.last_api_call < 1:  # Ensure at least 1 second between calls
            sleep_time = 1 - (current_time - self.last_api_call)
            logging.debug(f"Sleeping for {sleep_time} seconds")
            time_module.sleep(sleep_time)
        self.last_api_call = time_module.time()
        self.api_call_count += 1
        logging.debug(f"API call count: {self.api_call_count}")
        if self.api_call_count > 150:  # Fitbit's rate limit is 150 calls per hour
            logging.warning(f"Rate limit reached. Backing off for {self.backoff_time} seconds")
            time_module.sleep(self.backoff_time)
            self.backoff_time *= 2  # Exponential backoff
            if self.backoff_time > 3600:  # Cap at 1 hour
                self.backoff_time = 3600
            self.api_call_count = 0

    def make_api_call(self, func, **kwargs):
        try:
            return func(**kwargs)
        except fitbit.exceptions.HTTPUnauthorized:
            logging.info("Received HTTPUnauthorized, attempting to refresh token")
            self.refresh_access_token()
            return func(**kwargs)
        except fitbit.exceptions.HTTPTooManyRequests as e:
            retry_after = int(e.response.headers.get('Retry-After', 1))
            logging.warning(f"Rate limit exceeded. Retrying after {retry_after} seconds")
            time.sleep(retry_after)
            return func(**kwargs)
        except Exception as e:
            logging.error(f"Unexpected error in make_api_call: {e}")
            logging.error(traceback.format_exc())
            raise

    def refresh_access_token(self):
        try:
            # Prepare the token refresh request
            token_url = "https://api.fitbit.com/oauth2/token"
            headers = {
                "Authorization": "Basic " + base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode(),
                "Content-Type": "application/x-www-form-urlencoded"
            }
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token
            }

            # Make the token refresh request
            response = requests.post(token_url, headers=headers, data=data)
            response.raise_for_status()  # Raise an exception for bad responses
            tokens = response.json()

            # Update tokens
            self.access_token = tokens['access_token']
            self.refresh_token = tokens['refresh_token']
            self.config['access_token'] = self.access_token
            self.config['refresh_token'] = self.refresh_token

            # Reinitialize the Fitbit client with new tokens
            self.initialize_client()

            # Save the new tokens
            self.save_tokens()
            logging.info("Fitbit access token refreshed successfully")
        except KeyError as e:
            logging.error(f"KeyError in refresh_access_token: {e}")
            logging.error(f"Tokens received: {tokens}")
        except Exception as e:
            logging.error(f"Error refreshing Fitbit access token: {e}")
            logging.error(f"Full exception: {traceback.format_exc()}")

        if not self.access_token or not self.refresh_token:
            raise Exception("Failed to refresh access token")

    def save_tokens(self):
        # Update the tokens in the environment file
        env_file = os.path.join(os.path.dirname(__file__), '..', 'Variables.env')
        with open(env_file, 'r') as file:
            lines = file.readlines()
        
        with open(env_file, 'w') as file:
            for line in lines:
                if line.startswith('FITBIT_ACCESS_TOKEN='):
                    file.write(f"FITBIT_ACCESS_TOKEN={self.access_token}\n")
                elif line.startswith('FITBIT_REFRESH_TOKEN='):
                    file.write(f"FITBIT_REFRESH_TOKEN={self.refresh_token}\n")
                else:
                    file.write(line)
        
        logging.info("Fitbit tokens have been saved to environment file")

    def draw_progress_bar(self, screen, x, y, width, height, progress, goal):
        # Draw background
        pygame.draw.rect(screen, (000, 000, 000), (x, y, width, height))
        
        # Calculate progress width
        progress_width = int((progress / goal) * width)
        
        # Determine color based on progress
        if progress < 5000:
            color = (255, 0, 0)  # Red
        elif progress < 8000:
            color = (255, 255, 0)  # Yellow
        else:
            color = (0, 255, 0)  # Green
        
        # Draw progress
        pygame.draw.rect(screen, color, (x, y, progress_width, height))
        
        # Draw border
        pygame.draw.rect(screen, (100, 100, 100), (x, y, width, height), 2)

    def draw(self, screen, position):
        if self.font is None:
            try:
                self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE)
            except:
                print(f"Warning: Font '{FONT_NAME}' not found. Using default font.")
                self.font = pygame.font.Font(None, FONT_SIZE)  # Fallback to default font
        
        x, y = position
        
        # Draw progress bar for steps
        steps = int(self.data['steps']) if self.data['steps'] != 'N/A' else 0
        self.draw_progress_bar(screen, x, y, 200, 20, steps, self.step_goal)
        
        # Draw step count and goal
        step_text = f"Steps: {steps} / {self.step_goal}"
        step_surface = self.font.render(step_text, True, COLOR_FONT_DEFAULT)
        step_surface.set_alpha(TRANSPARENCY)
        screen.blit(step_surface, (x, y + 25))
        
        # Draw other Fitbit data
        y += 20  # Adjust starting y position for other data
        for i, (key, value) in enumerate(self.data.items()):
            if key != 'steps':  # Skip steps as we've already displayed it
                text = f"{key.replace('_', ' ').title()}: {value}"
                text_surface = self.font.render(text, True, COLOR_FONT_DEFAULT)
                text_surface.set_alpha(TRANSPARENCY)
                screen.blit(text_surface, (x, y + i * LINE_SPACING))

    def cleanup(self):
        pass