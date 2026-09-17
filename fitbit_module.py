import fitbit
import math
from datetime import datetime, timedelta
import time as time_module
import pygame
import logging
from config import (
    CONFIG, FONT_NAME, COLOR_FONT_DEFAULT, TRANSPARENCY, COLOR_FONT_SUBTITLE,
    COLOR_FONT_BODY, COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM, COLOR_ACCENT_GREEN,
    COLOR_ACCENT_RED, COLOR_ACCENT_AMBER, load_font,
)
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
from effects_kit import draw_trace_progress, draw_hero_glow
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
        self._moment_notify = None
        self._goal_hit_date = None  # date() the goal was last celebrated, so it fires once/day

    def set_moment_callback(self, callback):
        """Register a callback for Director moment triggers (event_director.py)."""
        self._moment_notify = callback

    def _check_goal_hit(self):
        if not self._moment_notify:
            return
        try:
            steps = int(self.data.get('steps', 0))
        except (TypeError, ValueError):
            return
        goal = self.step_goal or 10000
        today = datetime.now().date()
        if steps >= goal and self._goal_hit_date != today:
            self._goal_hit_date = today
            self._moment_notify('fitbit_goal_hit', {'steps': steps, 'goal': goal})
        
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
                self._check_goal_hit()
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
        except (fitbit.exceptions.HTTPUnauthorized, TokenExpiredError):
            logging.info("Fitbit token expired; refreshing and retrying")
            if not self.refresh_access_token():
                raise
            # refresh_access_token() rebuilt self.client, so re-resolve the
            # method on the NEW client - the old bound func still carries
            # the expired token and would 401 again.
            fresh = getattr(self.client, func.__name__)
            return fresh(**kwargs)
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
    def _draw_heart_icon(screen, cx, cy, size, color):
        r = size * 0.26
        pygame.draw.circle(screen, color, (int(cx - r * 0.9), int(cy - r * 0.3)), int(r))
        pygame.draw.circle(screen, color, (int(cx + r * 0.9), int(cy - r * 0.3)), int(r))
        pts = [(cx - r * 1.8, cy - r * 0.1), (cx, cy + r * 1.9), (cx + r * 1.8, cy - r * 0.1)]
        pygame.draw.polygon(screen, color, pts)

    @staticmethod
    def _draw_flame_icon(screen, cx, cy, size, color):
        r = size * 0.32
        pts = [
            (cx, cy - r * 1.3), (cx + r * 0.7, cy - r * 0.2), (cx + r * 0.55, cy + r * 0.9),
            (cx, cy + r * 1.3), (cx - r * 0.55, cy + r * 0.9), (cx - r * 0.7, cy - r * 0.2),
        ]
        pygame.draw.polygon(screen, color, pts)
        pygame.draw.circle(screen, color, (int(cx), int(cy + r * 0.2)), int(r * 0.35))

    @staticmethod
    def _draw_bolt_icon(screen, cx, cy, size, color):
        r = size * 0.34
        pts = [
            (cx + r * 0.15, cy - r * 1.2), (cx - r * 0.65, cy + r * 0.15), (cx - r * 0.05, cy + r * 0.15),
            (cx - r * 0.15, cy + r * 1.2), (cx + r * 0.65, cy - r * 0.15), (cx + r * 0.05, cy - r * 0.15),
        ]
        pygame.draw.polygon(screen, color, pts)

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
        progress grows, closing into a full square at the goal (the house
        progress idiom -- see effects_kit.draw_trace_progress)."""
        draw_trace_progress(screen, x, y, w, h, fraction,
                            self._progress_color(fraction), thickness)

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
                self.hero_font = load_font('light', 34)
                self.tile_label_font = load_font('regular', 10)
                self._fonts_ready = True

            label_color = COLOR_FONT_SUBTITLE
            value_color = COLOR_FONT_BODY

            align = position.get('align', 'left') if isinstance(position, dict) else 'left'

            from module_base import ModuleDrawHelper
            import theme
            current_y = ModuleDrawHelper.draw_module_title(
                screen, "Fitbit", x, y, width, align=align, accent_color=theme.module_accent('fitbit')
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

            fraction = steps_int / step_goal if step_goal else 0.0

            # A trace-frame square with the steps count as a hero number
            # inside it -- the frame itself already shows progress toward
            # goal, so the number just needs to be big, not prefixed with
            # "Steps:". Everything else (HR/sleep/active/cal) becomes a
            # small icon + number tile grid below -- no "Label: value"
            # text anywhere in this module.
            pad = 14
            side = min(width, 128)
            ring_r = side // 2
            frame_top = current_y
            frame_x = x + width - side if align == 'right' else x
            ring_cx, ring_cy = frame_x + ring_r, frame_top + ring_r
            from effects_kit import draw_ring_progress
            draw_ring_progress(screen, ring_cx, ring_cy, ring_r - 6, fraction,
                               self._progress_color(fraction), thickness=8)

            steps_surf = self.hero_font.render(f"{steps_int:,}", True, value_color)
            steps_surf.set_alpha(TRANSPARENCY)
            steps_y = ring_cy - steps_surf.get_height() // 2 - 6
            draw_hero_glow(screen, steps_surf, ring_cx - steps_surf.get_width() // 2,
                           steps_y, self._progress_color(fraction), intensity=0.4)
            screen.blit(steps_surf, (ring_cx - steps_surf.get_width() // 2, steps_y))
            unit_surf = self.tile_label_font.render("STEPS", True, COLOR_TEXT_DIM)
            unit_surf.set_alpha(TRANSPARENCY)
            screen.blit(unit_surf, (ring_cx - unit_surf.get_width() // 2,
                                    steps_y + steps_surf.get_height() + 2))

            # Icon tiles: 2 per row, filling to the module's edge.
            tiles = []
            hr = self.data.get('resting_heart_rate')
            if hr not in (None, 'N/A'):
                tiles.append((self._draw_heart_icon, str(hr), "BPM", COLOR_ACCENT_RED))
            sleep = self.data.get('sleep')
            if sleep not in (None, 'N/A'):
                tiles.append((None, str(sleep), "SLEEP", value_color))
            active = self.data.get('active_minutes')
            if active not in (None, 'N/A'):
                tiles.append((self._draw_bolt_icon, str(active), "ACTIVE MIN", COLOR_ACCENT_AMBER))
            cal = self.data.get('calories')
            if cal not in (None, 'N/A'):
                tiles.append((self._draw_flame_icon, str(cal), "CAL", COLOR_ACCENT_AMBER))

            tile_y = frame_top + side + 16
            tile_w = width // 2
            icon_r = 16
            for i, (icon_fn, value_text, unit_text, color) in enumerate(tiles):
                col = i % 2
                row = i // 2
                tx = x + col * tile_w
                ty = tile_y + row * 52
                icon_cx = tx + icon_r + 2 if align != 'right' else tx + tile_w - icon_r - 2
                if icon_fn:
                    icon_fn(screen, icon_cx, ty + icon_r, icon_r * 2, color)
                else:
                    z = self.small_font.render("z", True, color)
                    z.set_alpha(TRANSPARENCY)
                    screen.blit(z, (icon_cx - z.get_width() // 2, ty))
                val_surf = self.body_font.render(value_text, True, value_color)
                val_surf.set_alpha(TRANSPARENCY)
                unit_surf2 = self.tile_label_font.render(unit_text, True, COLOR_TEXT_DIM)
                unit_surf2.set_alpha(TRANSPARENCY)
                text_x = icon_cx + icon_r + 8 if align != 'right' else icon_cx - icon_r - 8 - val_surf.get_width()
                screen.blit(val_surf, (text_x, ty - 2))
                screen.blit(unit_surf2, (text_x, ty + val_surf.get_height() - 4))

        except Exception as e:
            logging.error(f"Error drawing Fitbit data: {e}")
            logging.error(traceback.format_exc())

    def cleanup(self):
        pass