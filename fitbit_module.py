import fitbit
import math
from datetime import datetime, timedelta
import time as time_module
import pygame
import logging
from config import CONFIG, FONT_NAME, COLOR_FONT_DEFAULT, TRANSPARENCY, COLOR_FONT_SUBTITLE, COLOR_FONT_BODY, COLOR_TEXT_SECONDARY
from api_tracker import api_tracker
import os
from pathlib import Path
import requests
import time
import traceback
from fitbit.api import Fitbit
from fitbit.exceptions import HTTPUnauthorized
from oauthlib.oauth2.rfc6749.errors import TokenExpiredError
from background_fetcher import BackgroundFetcher
import base64

class FitbitModule:
    # NOTE: The legacy Fitbit Web API this module uses is being retired by
    # Google in September 2026 in favour of the new Google Health API
    # (Google Cloud + Google OAuth, mandatory user re-consent). This module
    # will need a rewrite against that API before then. See:
    # https://developers.google.com/health/about
    def __init__(self, config, update_schedule):
        logging.info("Initializing FitbitModule")
        logging.warning(
            "Fitbit legacy Web API shuts down September 2026 - "
            "migration to the Google Health API will be required"
        )
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
        self.font = None
        self.step_goal = 10000  # Set the step goal
        self.last_skip_log = 0
        self._fetcher = BackgroundFetcher("fitbit")
        self._retry_after = 0  # unix time; set from a 429 Retry-After header
        self._api_retired = False  # set if the legacy API starts returning 410
        
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

    def _fetch_all_blocking(self):
        """Fetch activity, heart rate and sleep data (background thread).

        Returns a data dict in the same shape as self.data. The small
        pauses between calls are fine here - this never runs on the
        render loop.
        """
        result = dict(self.data)
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # Fetch activity data
        daily_data = self.make_api_call(self.client.activities, date=today)['summary']
        result['steps'] = daily_data.get('steps', 'N/A')
        result['calories'] = daily_data.get('caloriesOut', 'N/A')
        result['active_minutes'] = daily_data.get('fairlyActiveMinutes', 0) + daily_data.get('veryActiveMinutes', 0)

        # Fetch heart rate data
        try:
            time_module.sleep(1)  # be polite between calls
            heart_data = self.make_api_call(self.client.intraday_time_series, resource='activities/heart', base_date=today, detail_level='1min')
            result['resting_heart_rate'] = heart_data['activities-heart'][0]['value'].get('restingHeartRate', 'N/A')
        except Exception as e:
            logging.error(f"Error fetching heart rate data: {e}")
            result['resting_heart_rate'] = 'N/A'

        # Fetch sleep data
        try:
            time_module.sleep(1)
            sleep_data = self.make_api_call(self.client.sleep, date=yesterday)
            if 'summary' in sleep_data and 'totalMinutesAsleep' in sleep_data['summary']:
                total_minutes_asleep = sleep_data['summary']['totalMinutesAsleep']
                hours, minutes = divmod(total_minutes_asleep, 60)
                result['sleep'] = f"{hours:02}:{minutes:02}"
            else:
                result['sleep'] = 'N/A'
        except Exception as e:
            logging.error(f"Error fetching sleep data: {e}")
            result['sleep'] = 'N/A'

        return result

    def update(self):
        result = self._fetcher.take_result()
        if result is not None:
            ok, value = result
            if ok:
                self.data = value
                api_tracker.record("fitbit", "fitbit")
                logging.info("Fitbit data updated successfully")
            else:
                api_tracker.failure("fitbit", "fitbit")
                logging.error(f"Error updating Fitbit data: {value}")
                if '410' in str(value):
                    # Legacy Web API retired (September 2026): stop trying
                    self._api_retired = True
                    logging.error(
                        "Fitbit legacy API appears retired (HTTP 410). "
                        "Migrate to the Google Health API."
                    )
            self.last_update = datetime.now()

        if self._api_retired or not self.should_update():
            return
        if time.time() < self._retry_after:
            return
        if not api_tracker.allow("fitbit", "fitbit"):
            return
        if self.client is None:
            return
        self._fetcher.submit(self._fetch_all_blocking)

    def should_update(self):
        if self.last_update is None:
            return True
        return (datetime.now() - self.last_update).total_seconds() >= 3600

    def make_api_call(self, func, **kwargs):
        """Runs on the background fetch thread only."""
        try:
            return func(**kwargs)
        except fitbit.exceptions.HTTPUnauthorized:
            logging.info("Received HTTPUnauthorized, attempting to refresh token")
            self.refresh_access_token()
            return func(**kwargs)
        except fitbit.exceptions.HTTPTooManyRequests as e:
            # Do NOT sleep through the Retry-After window (it can be an
            # hour): remember when we may try again and give up for now.
            retry_after = int(e.response.headers.get('Retry-After', 3600))
            self._retry_after = time.time() + retry_after
            logging.warning(
                f"Fitbit rate limit exceeded; deferring updates for {retry_after}s"
            )
            raise
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

    @staticmethod
    def _progress_color(fraction):
        """Red below 50%, amber below 80%, green at/above goal."""
        if fraction < 0.5:
            return (220, 80, 80)
        if fraction < 0.8:
            return (240, 180, 40)
        return (80, 200, 120)

    def draw_step_frame(self, screen, x, y, w, h, fraction, thickness=3):
        """Trace a coloured line around the module's outline as step
        progress grows, closing into a full square at the goal.

        Starts at the top-left and runs clockwise (top -> right -> bottom
        -> left). Only the filled coloured portion is drawn - no track.
        """
        fraction = max(0.0, min(fraction, 1.0))
        if fraction <= 0:
            return
        t = thickness
        # Draw onto a SRCALPHA layer so colours blend softly on the glass
        surf = pygame.Surface((w + t, h + t), pygame.SRCALPHA)
        inset = t / 2.0
        x0, y0 = inset, inset
        x1, y1 = w - inset, h - inset

        color = (*self._progress_color(fraction), 230)
        perim = 2 * ((x1 - x0) + (y1 - y0))
        remaining = fraction * perim
        edges = [
            ((x0, y0), (x1, y0)),   # top
            ((x1, y0), (x1, y1)),   # right
            ((x1, y1), (x0, y1)),   # bottom
            ((x0, y1), (x0, y0)),   # left
        ]
        for (ax, ay), (bx, by) in edges:
            if remaining <= 0:
                break
            seg = math.hypot(bx - ax, by - ay)
            if seg <= 0:
                continue
            if remaining >= seg:
                pygame.draw.line(surf, color, (ax, ay), (bx, by), t)
                remaining -= seg
            else:
                f = remaining / seg
                pygame.draw.line(
                    surf, color, (ax, ay),
                    (ax + (bx - ax) * f, ay + (by - ay) * f), t,
                )
                remaining = 0
        screen.blit(surf, (x, y))

    def draw(self, screen, position):
        """Draw Fitbit data -- floating text on black, no background."""
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 200)
            else:
                x, y = position
                width, height = 300, 200

            styling = CONFIG.get('module_styling', {})
            line_height = styling.get('spacing', {}).get('line_height', 28)

            if not hasattr(self, '_fonts_ready') or not self._fonts_ready:
                from module_base import ModuleDrawHelper
                title_f, body_f, small_f = ModuleDrawHelper.get_fonts()
                self.title_font = title_f
                self.body_font = body_f
                self.small_font = small_f
                self._fonts_ready = True

            label_color = COLOR_FONT_SUBTITLE
            value_color = COLOR_FONT_BODY

            align = position.get('align', 'left') if isinstance(position, dict) else 'left'

            from module_base import ModuleDrawHelper
            current_y = ModuleDrawHelper.draw_module_title(
                screen, "Fitbit", x, y, width, align=align
            )

            if self._api_retired:
                msg = self.body_font.render("Fitbit API retired", True, label_color)
                ModuleDrawHelper.blit_aligned(screen, msg, x, current_y, width, align)
                return

            # Check if we have data
            if not self.data:
                no_data_text = self.body_font.render("No Fitbit data available", True, value_color)
                ModuleDrawHelper.blit_aligned(screen, no_data_text, x, current_y, width, align)
                return

            # Get steps and goal for progress bar
            steps = self.data.get('steps', '0')
            step_goal = 10000  # Default
            if 'goals' in self.data and 'steps' in self.data['goals']:
                step_goal = int(self.data['goals']['steps'])

            # Try to convert steps to int for progress bar
            try:
                steps_int = int(steps)
            except Exception:
                steps_int = 0

            # Step progress frame: a square anchored to the module's outer
            # edge and sitting BELOW the title so it never covers text.
            # Closes into a full square at the goal.
            fraction = steps_int / step_goal if step_goal else 0.0
            frame_top = current_y - 2
            frame_side = max(60, (y + height - 10) - frame_top)
            if align == 'right':
                frame_x = x + width - frame_side
                if frame_x < x:
                    frame_x, frame_side = x, width
            else:
                frame_side = min(frame_side, width)
                frame_x = x
            self.draw_step_frame(screen, frame_x, frame_top, frame_side, frame_side, fraction)

            # Keep text off the frame line with a little inner padding
            inner = 14
            cw = width - inner

            steps_label = self.body_font.render("Steps:", True, label_color)
            steps_value = self.body_font.render(str(steps), True, value_color)
            steps_label.set_alpha(TRANSPARENCY)
            steps_value.set_alpha(TRANSPARENCY)
            combined_w = steps_label.get_width() + 5 + steps_value.get_width()
            if align == 'right':
                sx = x + cw - combined_w
            else:
                sx = x
            screen.blit(steps_label, (sx, current_y))
            screen.blit(steps_value, (sx + steps_label.get_width() + 5, current_y))
            current_y += line_height

            if 'resting_heart_rate' in self.data and self.data['resting_heart_rate'] != 'N/A':
                hr_text = f"HR: {self.data['resting_heart_rate']} bpm"
                hr_surf = self.body_font.render(hr_text, True, value_color)
                hr_surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(screen, hr_surf, x, current_y, cw, align)
                current_y += line_height

            if 'sleep' in self.data and self.data['sleep'] != 'N/A':
                sleep_text = f"Sleep: {self.data['sleep']}"
                sleep_surf = self.body_font.render(sleep_text, True, value_color)
                sleep_surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(screen, sleep_surf, x, current_y, cw, align)
                current_y += line_height

            if 'active_minutes' in self.data:
                active_text = f"Active: {self.data['active_minutes']} min"
                active_surf = self.body_font.render(active_text, True, value_color)
                active_surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(screen, active_surf, x, current_y, cw, align)
                current_y += line_height

            if 'calories' in self.data and self.data['calories'] != 'N/A':
                cal_text = f"Cal: {self.data['calories']}"
                cal_surf = self.body_font.render(cal_text, True, value_color)
                cal_surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(screen, cal_surf, x, current_y, cw, align)
            
        except Exception as e:
            logging.error(f"Error drawing Fitbit data: {e}")
            logging.error(traceback.format_exc())

    def cleanup(self):
        pass