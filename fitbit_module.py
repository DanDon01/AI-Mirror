import fitbit
import math
from datetime import datetime, timedelta
import time as time_module
import pygame
import logging
from config import (
    CONFIG, FONT_NAME, COLOR_FONT_DEFAULT, TRANSPARENCY, COLOR_FONT_SUBTITLE,
    COLOR_FONT_BODY, COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM, COLOR_TEXT_ACCENT,
    COLOR_ACCENT_GREEN, COLOR_ACCENT_RED, COLOR_ACCENT_AMBER, load_font,
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
from effects_kit import draw_hero_glow
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
        # Built up from real observed updates over the runtime session (no
        # extra API call) -- starts empty on restart, fills in over the day.
        self._step_history = []
        self._step_history_date = None

    def set_moment_callback(self, callback):
        """Register a callback for Director moment triggers (event_director.py)."""
        self._moment_notify = callback

    def _record_step_history(self):
        """One sample per hourly refresh, reset at midnight -- a real
        (if coarse) today-so-far trend, built from data already being
        fetched rather than a new API call."""
        try:
            steps = int(self.data.get('steps', 0))
        except (TypeError, ValueError):
            return
        today = datetime.now().date()
        if self._step_history_date != today:
            self._step_history = []
            self._step_history_date = today
        if not self._step_history or self._step_history[-1] != steps:
            self._step_history.append(steps)
            self._step_history = self._step_history[-24:]

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
            # The intraday call above already returns a full per-minute
            # dataset for today -- only the resting summary was ever used.
            # Downsample it for a real BPM trend line instead of a
            # decorative fake waveform.
            dataset = heart_data.get('activities-heart-intraday', {}).get('dataset', [])
            if dataset:
                values = [pt['value'] for pt in dataset if 'value' in pt]
                step = max(1, len(values) // 60)
                result['hr_trend'] = values[::step][-60:]
            else:
                result['hr_trend'] = []
        except Exception as e:
            logging.error(f"Error fetching heart rate data: {e}")
            result['resting_heart_rate'] = 'N/A'
            result['hr_trend'] = []

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
                self._record_step_history()
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
    def _draw_heart_icon(screen, cx, cy, size, color, scale=1.0):
        r = size * 0.26 * scale
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

    def _readiness_fraction(self, steps_frac, sleep_frac, resting_hr):
        """A simple composite from real inputs (not a proprietary score --
        this mirror doesn't have one to show). Steps and sleep weigh most;
        resting HR contributes a coarse health-band signal."""
        if resting_hr in (None, 'N/A'):
            hr_score = 0.6
        else:
            try:
                hr = float(resting_hr)
                if hr <= 70:
                    hr_score = 1.0
                elif hr <= 85:
                    hr_score = 0.6
                else:
                    hr_score = 0.3
            except (TypeError, ValueError):
                hr_score = 0.6
        return max(0.0, min(1.0, 0.4 * steps_frac + 0.35 * sleep_frac + 0.25 * hr_score))

    def draw(self, screen, position):
        """BIOMETRICS: a small habitat's vital-signs readout -- circular
        gauges, real trend lines and icons, no "Label: value" text. Not a
        rectangular card (see AI-Mirror.py's NO_PANEL_FRAME) -- its own
        arcs and rings provide the structure."""
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 200)
            else:
                x, y = position
                width, height = 300, 200

            if not hasattr(self, '_fonts_ready') or not self._fonts_ready:
                from module_base import ModuleDrawHelper
                title_f, body_f, small_f = ModuleDrawHelper.get_fonts()
                self.title_font = title_f
                self.body_font = body_f
                self.small_font = small_f
                self.hero_font = load_font('light', 34)
                self.stat_font = load_font('light', 22)
                self.tile_label_font = load_font('regular', 10)
                self._fonts_ready = True

            label_color = COLOR_FONT_SUBTITLE
            value_color = COLOR_FONT_BODY

            align = position.get('align', 'left') if isinstance(position, dict) else 'left'

            from module_base import ModuleDrawHelper
            from effects_kit import draw_ring_progress, draw_sparkline
            import theme
            accent = theme.module_accent('fitbit')
            current_y = ModuleDrawHelper.draw_module_title(
                screen, "Biometrics", x, y, width, align=align, accent_color=accent
            )

            if self._api_retired:
                msg = self.body_font.render("Fitbit API retired", True, label_color)
                ModuleDrawHelper.blit_aligned(screen, msg, x, current_y, width, align)
                return
            if not self.data:
                no_data_text = self.body_font.render("Connecting...", True, value_color)
                ModuleDrawHelper.blit_aligned(screen, no_data_text, x, current_y, width, align)
                return

            step_goal = 10000
            if 'goals' in self.data and 'steps' in self.data['goals']:
                step_goal = int(self.data['goals']['steps'])
            try:
                steps_int = int(self.data.get('steps', 0))
            except (TypeError, ValueError):
                steps_int = 0
            steps_frac = steps_int / step_goal if step_goal else 0.0

            sleep_text = self.data.get('sleep')
            sleep_hours = None
            if sleep_text not in (None, 'N/A') and ':' in str(sleep_text):
                h, m = sleep_text.split(':')
                sleep_hours = int(h) + int(m) / 60.0
            sleep_target = 8.0
            sleep_frac = min(1.0, (sleep_hours or 0) / sleep_target)

            hr = self.data.get('resting_heart_rate')
            hr_trend = self.data.get('hr_trend') or []

            cx = x + width // 2

            # -- Steps: the big ring, with today-so-far trend beneath it --
            ring_r = min(width, 150) // 2 - 4
            ring_cy = current_y + ring_r + 6
            draw_ring_progress(screen, cx, ring_cy, ring_r - 4, steps_frac,
                               self._progress_color(steps_frac), thickness=8)
            steps_surf = self.hero_font.render(f"{steps_int:,}", True, value_color)
            steps_surf.set_alpha(TRANSPARENCY)
            steps_y = ring_cy - steps_surf.get_height() // 2 - 6
            draw_hero_glow(screen, steps_surf, cx - steps_surf.get_width() // 2,
                           steps_y, self._progress_color(steps_frac), intensity=0.4)
            screen.blit(steps_surf, (cx - steps_surf.get_width() // 2, steps_y))
            unit_surf = self.tile_label_font.render("STEPS TODAY", True, COLOR_TEXT_DIM)
            unit_surf.set_alpha(TRANSPARENCY)
            screen.blit(unit_surf, (cx - unit_surf.get_width() // 2,
                                    steps_y + steps_surf.get_height() + 2))

            draw_y = ring_cy + ring_r + 18
            if len(self._step_history) >= 2 and draw_y + 24 < y + height:
                spark_w = min(width - 20, 180)
                draw_sparkline(screen, cx - spark_w // 2, draw_y, spark_w, 20,
                               self._step_history, self._progress_color(steps_frac), vmin=0)
                draw_y += 30

            # -- Heart rate: pulsing icon (real BPM sets the pulse rate) --
            if hr not in (None, 'N/A') and draw_y + 40 < y + height:
                try:
                    bpm = float(hr)
                    pulse_hz = bpm / 60.0
                except (TypeError, ValueError):
                    bpm, pulse_hz = None, 1.0
                phase = (pygame.time.get_ticks() / 1000.0) * pulse_hz
                import math as _math
                scale = 1.0 + 0.18 * max(0.0, _math.sin(phase * _math.tau))
                icon_x = x + 16
                self._draw_heart_icon(screen, icon_x, draw_y + 14, 30, COLOR_ACCENT_RED, scale=scale)
                bpm_surf = self.stat_font.render(f"{hr}", True, value_color)
                bpm_surf.set_alpha(TRANSPARENCY)
                unit2 = self.tile_label_font.render("BPM RESTING", True, COLOR_TEXT_DIM)
                unit2.set_alpha(TRANSPARENCY)
                screen.blit(bpm_surf, (icon_x + 22, draw_y))
                screen.blit(unit2, (icon_x + 22 + bpm_surf.get_width() + 8,
                                    draw_y + bpm_surf.get_height() - unit2.get_height() - 2))
                if len(hr_trend) >= 2:
                    spark_x = icon_x + 22
                    draw_sparkline(screen, spark_x, draw_y + bpm_surf.get_height() + 2,
                                  width - (spark_x - x) - 10, 16, hr_trend, COLOR_ACCENT_RED)
                draw_y += 58

            # -- Sleep: a half-arc (distinct from the full steps ring) --
            if sleep_hours is not None and draw_y + 60 < y + height:
                arc_r = min(width, 140) // 2 - 10
                arc_cy = draw_y + 6
                draw_ring_progress(screen, cx, arc_cy, arc_r, sleep_frac, COLOR_TEXT_ACCENT,
                                   thickness=7, start_deg=160, end_deg=380)
                sleep_surf = self.stat_font.render(sleep_text, True, value_color)
                sleep_surf.set_alpha(TRANSPARENCY)
                screen.blit(sleep_surf, (cx - sleep_surf.get_width() // 2, arc_cy - 6))
                unit3 = self.tile_label_font.render("SLEEP", True, COLOR_TEXT_DIM)
                unit3.set_alpha(TRANSPARENCY)
                screen.blit(unit3, (cx - unit3.get_width() // 2, arc_cy + sleep_surf.get_height() - 4))
                draw_y = arc_cy + arc_r * 0.55 + 20

            # -- Readiness: small composite ring, real inputs, no card --
            if draw_y + 60 < y + height:
                readiness = self._readiness_fraction(steps_frac, sleep_frac, hr)
                r_r = 30
                r_cx = x + r_r + 4
                r_cy = draw_y + r_r
                r_color = self._progress_color(readiness)
                draw_ring_progress(screen, r_cx, r_cy, r_r - 5, readiness, r_color, thickness=5)
                pct_surf = self.tile_label_font.render(f"{int(readiness * 100)}%", True, value_color)
                pct_surf.set_alpha(TRANSPARENCY)
                screen.blit(pct_surf, (r_cx - pct_surf.get_width() // 2, r_cy - pct_surf.get_height() // 2))
                label = self.tile_label_font.render("READINESS", True, COLOR_TEXT_DIM)
                label.set_alpha(TRANSPARENCY)
                screen.blit(label, (r_cx + r_r + 10, r_cy - label.get_height() // 2))

        except Exception as e:
            logging.error(f"Error drawing Fitbit data: {e}")
            logging.error(traceback.format_exc())

    def cleanup(self):
        pass