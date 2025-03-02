import fitbit
from datetime import datetime, timedelta
import time as time_module
import pygame
import logging
from config import CONFIG, FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, LINE_SPACING, TRANSPARENCY, COLOR_BG_MODULE_ALPHA, COLOR_BG_HEADER_ALPHA, COLOR_FONT_SUBTITLE, COLOR_FONT_BODY
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
        self.last_skip_log = 0
        
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
        current_time = time.time()
        if not self.should_update():
            if current_time - self.last_skip_log > 60:  # Log only once per minute
                logging.debug("Skipping Fitbit update: Not enough time has passed since last update")
                self.last_skip_log = current_time
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
            # Log the current state
            logging.info("Starting token refresh process")
            logging.debug(f"Client ID: {self.client_id[:5]}...")  # Log only first 5 chars for security
            
            # Prepare the token refresh request
            token_url = "https://api.fitbit.com/oauth2/token"
            auth_string = f"{self.client_id}:{self.client_secret}"
            auth_header = base64.b64encode(auth_string.encode()).decode()
            
            headers = {
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token
            }

            # Make the token refresh request
            logging.debug("Sending refresh token request")
            response = requests.post(token_url, headers=headers, data=data)
            
            # Log the response status
            logging.debug(f"Refresh token response status: {response.status_code}")
            
            if response.status_code != 200:
                logging.error(f"Token refresh failed with status {response.status_code}")
                logging.error(f"Response content: {response.text}")
                raise Exception(f"Token refresh failed: {response.text}")

            tokens = response.json()
            
            # Validate the response contains required tokens
            if 'access_token' not in tokens or 'refresh_token' not in tokens:
                logging.error("Invalid token response format")
                logging.error(f"Received tokens keys: {tokens.keys()}")
                raise KeyError("Missing required tokens in response")

            # Update tokens
            self.access_token = tokens['access_token']
            self.refresh_token = tokens['refresh_token']
            self.config['access_token'] = self.access_token
            self.config['refresh_token'] = self.refresh_token

            # Save the new tokens
            self.save_tokens()
            
            # Reinitialize the client with new tokens
            self.initialize_client()
            
            logging.info("Token refresh completed successfully")
            return True

        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during token refresh: {e}")
            return False
        except KeyError as e:
            logging.error(f"KeyError in refresh_access_token: {e}")
            logging.error(f"Tokens received: {tokens}")
            return False
        except Exception as e:
            logging.error(f"Error refreshing Fitbit access token: {e}")
            logging.error(f"Full exception: {traceback.format_exc()}")
            return False

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
        # Fix width to prevent going off-screen
        width = min(width, 250)  # Limit max width to 250px
        height = height * 2      # Double the height
        
        # Draw background
        bg_color = COLOR_BG_MODULE_ALPHA
        pygame.draw.rect(screen, bg_color, (x, y, width, height))
        
        # Calculate progress width, ensuring it doesn't exceed total width
        progress_width = min(int((progress / goal) * width), width)
        
        # Determine color based on progress
        if progress < goal * 0.5:
            color = (255, 100, 100)  # Red
        elif progress < goal * 0.8:
            color = (255, 255, 100)  # Yellow
        else:
            color = (100, 255, 100)  # Green
        
        # Draw progress
        pygame.draw.rect(screen, color, (x, y, progress_width, height))
        
        # Draw border
        pygame.draw.rect(screen, (100, 100, 100), (x, y, width, height), 2)

    def draw(self, screen, position):
        """Draw Fitbit data with consistent styling"""
        try:
            # Extract position
            if isinstance(position, dict):
                x, y = position['x'], position['y']
            else:
                x, y = position
            
            # Get styling from config
            styling = CONFIG.get('module_styling', {})
            fonts = styling.get('fonts', {})
            backgrounds = styling.get('backgrounds', {})
            
            # Get module dimensions from config
            module_dims = styling.get('module_dimensions', {}).get('standard', {})
            module_width = module_dims.get('width', 225)
            module_height = module_dims.get('height', 200)
            header_height = module_dims.get('header_height', 40)
            
            # Get styles for drawing
            radius = styling.get('radius', 15)
            padding = styling.get('spacing', {}).get('padding', 10)
            line_height = styling.get('spacing', {}).get('line_height', 22)
            
            # Initialize fonts if needed
            if not hasattr(self, 'title_font'):
                title_size = fonts.get('title', {}).get('size', 24)
                body_size = fonts.get('body', {}).get('size', 16)
                small_size = fonts.get('small', {}).get('size', 14)
                
                self.title_font = pygame.font.SysFont(FONT_NAME, title_size)
                self.body_font = pygame.font.SysFont(FONT_NAME, body_size)
                self.small_font = pygame.font.SysFont(FONT_NAME, small_size)
            
            # Color for labels (use subtitle color from config)
            label_color = COLOR_FONT_SUBTITLE
            # Color for values (use body color from config)
            value_color = COLOR_FONT_BODY
            
            # Draw module background
            module_rect = pygame.Rect(x-padding, y-padding, module_width, module_height)
            header_rect = pygame.Rect(x-padding, y-padding, module_width, header_height)
            
            # Draw background with styling from config
            try:
                self.effects.draw_rounded_rect(screen, module_rect, bg_color, radius=radius, alpha=0)
                self.effects.draw_rounded_rect(screen, header_rect, bg_color, radius=radius, alpha=0)
            except:
                # Fallback if effects fail
                from config import draw_module_background_fallback
                draw_module_background_fallback(screen, x, y, module_width, module_height, padding)
            
            # Draw title
            title_color = fonts.get('title', {}).get('color', COLOR_FONT_DEFAULT)
            title_text = self.title_font.render("Fitbit", True, title_color)
            screen.blit(title_text, (x + padding, y + padding))
            
            # Draw Fitbit data
            current_y = y + header_height + 5  # Start below title
            
            # Check if we have data
            if not self.data:
                no_data_text = self.body_font.render("No Fitbit data available", True, value_color)
                screen.blit(no_data_text, (x + padding, current_y))
                return
            
            # Get steps and goal for progress bar
            steps = self.data.get('steps', '0')
            step_goal = 10000  # Default
            if 'goals' in self.data and 'steps' in self.data['goals']:
                step_goal = int(self.data['goals']['steps'])
            
            # Try to convert steps to int for progress bar
            try:
                steps_int = int(steps)
            except:
                steps_int = 0
            
            # Draw progress bar for steps
            self.draw_progress_bar(screen, x + padding, current_y, module_width - 2*padding, 10, steps_int, step_goal)
            current_y += 15  # Space after progress bar
            
            # Display Steps and Goal with different colors for label vs value
            steps_label = self.body_font.render("Steps:", True, label_color)
            steps_value = self.body_font.render(str(steps), True, value_color)
            
            # Draw them side by side
            screen.blit(steps_label, (x + padding, current_y))
            # Position value right after label
            label_width = steps_label.get_width()
            screen.blit(steps_value, (x + padding + label_width + 5, current_y))
            
            # Display goal if available
            if 'goals' in self.data and 'steps' in self.data['goals']:
                goal_label = self.small_font.render("Goal:", True, label_color)
                goal_value = self.small_font.render(str(self.data['goals']['steps']), True, value_color)
                screen.blit(goal_label, (x + padding + 150, current_y))
                screen.blit(goal_value, (x + padding + 150 + goal_label.get_width() + 5, current_y))
            
            current_y += line_height
            
            # Use the same pattern for other metrics
            # Heart rate
            if 'resting_heart_rate' in self.data and self.data['resting_heart_rate'] != 'N/A':
                hr_label = self.body_font.render("Resting HR:", True, label_color)
                hr_value = self.body_font.render(f"{self.data['resting_heart_rate']} bpm", True, value_color)
                screen.blit(hr_label, (x + padding, current_y))
                screen.blit(hr_value, (x + padding + hr_label.get_width() + 5, current_y))
                current_y += line_height
            
            # Sleep data
            if 'sleep' in self.data and self.data['sleep'] != 'N/A':
                sleep_label = self.body_font.render("Sleep:", True, label_color)
                sleep_value = self.body_font.render(self.data['sleep'], True, value_color)
                screen.blit(sleep_label, (x + padding, current_y))
                screen.blit(sleep_value, (x + padding + sleep_label.get_width() + 5, current_y))
                current_y += line_height
            
            # Active minutes
            if 'active_minutes' in self.data:
                active_label = self.body_font.render("Active:", True, label_color)
                active_value = self.body_font.render(f"{self.data['active_minutes']} min", True, value_color)
                screen.blit(active_label, (x + padding, current_y))
                screen.blit(active_value, (x + padding + active_label.get_width() + 5, current_y))
                current_y += line_height
            
            # Calories
            if 'calories' in self.data and self.data['calories'] != 'N/A':
                cal_label = self.body_font.render("Calories:", True, label_color)
                cal_value = self.body_font.render(self.data['calories'], True, value_color)
                screen.blit(cal_label, (x + padding, current_y))
                screen.blit(cal_value, (x + padding + cal_label.get_width() + 5, current_y))
            
        except Exception as e:
            logging.error(f"Error drawing Fitbit data: {e}")
            logging.error(traceback.format_exc())

    def cleanup(self):
        pass