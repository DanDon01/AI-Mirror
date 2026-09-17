import fitbit
import math
from datetime import datetime, timedelta
import time as time_module
import pygame
import logging
from config import (
    COLOR_FONT_BODY, COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM,
    COLOR_ACCENT_GREEN, COLOR_ACCENT_AMBER, load_font,
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
import base64

_ECG_SAMPLES = None

# One cardiac cycle as (position, amplitude) control points: P wave, the
# sharp QRS complex, then the T wave. The QRS is interpolated linearly
# because it genuinely is a spike; everything else is smoothed.
_ECG_KEYS = [
    (0.00, 0.00), (0.08, 0.00), (0.13, 0.13), (0.19, 0.15), (0.24, 0.00),
    (0.29, 0.00), (0.32, -0.10), (0.35, 1.00), (0.385, -0.32), (0.42, 0.00),
    (0.50, 0.00), (0.58, 0.17), (0.66, 0.25), (0.74, 0.06), (0.80, 0.00),
    (1.00, 0.00),
]


def _ecg_beat(n=192):
    """Sampled single-beat ECG waveform, built once and reused."""
    global _ECG_SAMPLES
    if _ECG_SAMPLES is not None:
        return _ECG_SAMPLES
    out = []
    for i in range(n):
        t = i / (n - 1)
        value = 0.0
        for j in range(len(_ECG_KEYS) - 1):
            t0, v0 = _ECG_KEYS[j]
            t1, v1 = _ECG_KEYS[j + 1]
            if t0 <= t <= t1:
                f = (t - t0) / max(1e-6, t1 - t0)
                sharp = t0 >= 0.29 and t1 <= 0.42
                if not sharp:
                    f = f * f * (3 - 2 * f)
                value = v0 + (v1 - v0) * f
                break
        out.append(value)
    _ECG_SAMPLES = out
    return out


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
        total_distance = next(
            (d.get('distance') for d in daily_data.get('distances', [])
             if d.get('activity') == 'total'), None)
        result['distance'] = total_distance if total_distance is not None else 'N/A'

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
                if values:
                    result['hr_min'] = min(values)
                    result['hr_max'] = max(values)
                    result['hr_avg'] = int(round(sum(values) / len(values)))
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
            result.update(self._extract_sleep_stages(sleep_data))
        except Exception as e:
            logging.error(f"Error fetching sleep data: {e}")
            result['sleep'] = 'N/A'
            result['sleep_stages'] = []

        # Fetch a real 7-day step history for the weekly graph. Without
        # this the only history available is what this process has
        # observed since it started, which is empty after every restart.
        try:
            time_module.sleep(1)
            weekly = self.make_api_call(
                self.client.time_series, resource='activities/steps', period='7d'
            )
            series = weekly.get('activities-steps', [])
            result['weekly_steps'] = [
                (entry.get('dateTime', ''), int(float(entry.get('value', 0) or 0)))
                for entry in series
            ]
        except Exception as e:
            logging.error(f"Error fetching weekly step history: {e}")
            result['weekly_steps'] = []

        return result

    @staticmethod
    def _extract_sleep_stages(sleep_data):
        """Pull a real stage-by-stage sleep breakdown out of the response.

        Modern trackers return `levels.data` (deep/light/rem/wake segments);
        older ones only return `minuteData` (asleep/restless/awake). Both
        are handled, and when neither is present the caller gets an empty
        list and draws a plain duration bar rather than inventing a
        plausible-looking stage split.
        """
        out = {'sleep_stages': [], 'sleep_start': None, 'sleep_end': None}
        logs = sleep_data.get('sleep') or []
        if not logs:
            return out

        main = next((log for log in logs if log.get('isMainSleep')), None)
        if main is None:
            main = max(logs, key=lambda log: log.get('timeInBed', 0) or 0)

        for key, field in (('sleep_start', 'startTime'), ('sleep_end', 'endTime')):
            raw = main.get(field)
            if raw and 'T' in str(raw):
                out[key] = str(raw).split('T')[1][:5]

        segments = (main.get('levels') or {}).get('data') or []
        if segments:
            out['sleep_stages'] = [
                (str(seg.get('level', 'light')).lower(), int(seg.get('seconds', 0) or 0))
                for seg in segments if seg.get('seconds')
            ]
            return out

        # Classic format: one entry per minute, value 1=asleep 2=restless 3=awake
        minute_data = main.get('minuteData') or []
        if minute_data:
            collapsed = []
            level_for = {'1': 'light', '2': 'restless', '3': 'wake'}
            for entry in minute_data:
                level = level_for.get(str(entry.get('value', '1')), 'light')
                if collapsed and collapsed[-1][0] == level:
                    collapsed[-1][1] += 60
                else:
                    collapsed.append([level, 60])
            out['sleep_stages'] = [(lvl, secs) for lvl, secs in collapsed]
        return out

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

    # ------------------------------------------------------------------
    # BIOMETRIC MONITOR rendering
    # ------------------------------------------------------------------

    def _ensure_fonts(self):
        if getattr(self, '_fonts_ready', False):
            return
        self.f_title = load_font('light', 25)
        self.f_hero = load_font('light', 40)
        self.f_value = load_font('light', 21)
        self.f_small = load_font('light', 14)
        self.f_micro = load_font('regular', 10)
        self.f_nano = load_font('regular', 8)
        self._text_cache = {}
        self._fonts_ready = True

    def _text(self, font_key, text, color, spacing=0):
        """Cached text render with optional letter-spacing. Tracked
        uppercase is the house label style, and pygame has no native
        tracking, so spaced glyphs are composited once and reused."""
        key = (font_key, text, color, spacing)
        cached = self._text_cache.get(key)
        if cached is not None:
            return cached
        font = getattr(self, font_key)
        if spacing <= 0:
            surf = font.render(text, True, color)
        else:
            glyphs = [font.render(ch, True, color) for ch in text]
            w = sum(g.get_width() for g in glyphs) + spacing * max(0, len(glyphs) - 1)
            surf = pygame.Surface((max(1, w), font.get_height()), pygame.SRCALPHA)
            gx = 0
            for g in glyphs:
                surf.blit(g, (gx, 0))
                gx += g.get_width() + spacing
        if len(self._text_cache) > 400:
            self._text_cache.clear()
        self._text_cache[key] = surf
        return surf

    STAGE_COLORS = {
        'deep': (52, 92, 224),
        'light': (84, 168, 238),
        'rem': (192, 96, 220),
        'restless': (120, 150, 200),
        'wake': (240, 168, 88),
        'awake': (240, 168, 88),
    }

    def _status(self, readiness, resting_hr):
        """A real status word from real bands -- not decoration."""
        try:
            hr = float(resting_hr)
        except (TypeError, ValueError):
            hr = None
        if hr is not None and hr > 90:
            return "ELEVATED", COLOR_ACCENT_AMBER
        if readiness < 0.4:
            return "RECOVERING", COLOR_ACCENT_AMBER
        return "NOMINAL", COLOR_ACCENT_GREEN

    def _draw_ecg(self, screen, x, y, w, h, color, bpm):
        """A scrolling ECG trace whose beat spacing is driven by the real
        BPM -- at 58 bpm the complexes genuinely arrive once a second."""
        beat = _ecg_beat()
        n = len(beat)
        try:
            rate = float(bpm)
        except (TypeError, ValueError):
            rate = 60.0
        rate = max(35.0, min(190.0, rate))

        # Grid: ECG-paper ruling, kept well under the trace so it reads as
        # calibration rather than competing with the waveform.
        grid = (86, 116, 146)
        for gx in range(int(x), int(x + w), 18):
            pygame.draw.line(screen, (*grid, 30), (gx, y), (gx, y + h), 1)
        for i in range(1, 4):
            gy = y + h * i / 4
            pygame.draw.line(screen, (*grid, 30), (x, gy), (x + w, gy), 1)

        beat_px = max(30.0, w / 3.1)
        scroll = (pygame.time.get_ticks() / 1000.0) * beat_px * (rate / 60.0)
        mid = y + h / 2.0
        amp = h * 0.46
        pts = []
        for px in range(int(w)):
            idx = int(((scroll + px) / beat_px % 1.0) * n)
            pts.append((x + px, mid - beat[idx] * amp))
        if len(pts) < 2:
            return
        pygame.draw.lines(screen, (*color, 210), False, pts, 2)
        # Brighter leading edge, like a live monitor's sweep head
        tail = pts[-34:]
        if len(tail) >= 2:
            pygame.draw.lines(screen, (255, 255, 255, 240), False, tail, 2)
        pygame.draw.circle(screen, (255, 255, 255, 255),
                           (int(pts[-1][0]), int(pts[-1][1])), 3)

    def _draw_leader(self, screen, from_pt, to_x, label_surf, value_surf, color, side):
        """A schematic annotation line from a point on the body out to a
        micro-labelled stub -- the graphical relationship between the scan
        figure and its readouts."""
        fx, fy = from_pt
        pygame.draw.circle(screen, (*color, 230), (int(fx), int(fy)), 2)
        pygame.draw.line(screen, (*color, 120), (fx, fy), (to_x, fy), 1)
        tick = 5
        pygame.draw.line(screen, (*color, 170), (to_x, fy - tick), (to_x, fy + tick), 1)
        pad = 5
        if side == 'right':
            lx = to_x + pad
        else:
            lx = to_x - pad - max(label_surf.get_width(), value_surf.get_width())
        screen.blit(label_surf, (lx, fy - label_surf.get_height() - 1))
        screen.blit(value_surf, (lx, fy + 1))

    def _draw_header(self, screen, x, y, w, accent, status_text, status_color):
        title = self._text('f_title', "BIOMETRIC MONITOR", COLOR_FONT_BODY, spacing=1)
        screen.blit(title, (x, y))
        sub_y = y + title.get_height() + 2
        sub = self._text('f_nano', "CARDIOVASCULAR  LOCOMOTION  RECOVERY",
                         COLOR_TEXT_DIM, spacing=2)
        screen.blit(sub, (x, sub_y))

        # Status rides the subtitle line, where it cannot collide with the
        # title however wide the title renders.
        st = self._text('f_micro', status_text, status_color, spacing=2)
        st_x = x + w - st.get_width()
        screen.blit(st, (st_x, sub_y - 2))
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 520.0)
        pygame.draw.circle(screen, (*status_color, int(120 + 135 * pulse)),
                           (int(st_x - 9), int(sub_y - 2 + st.get_height() // 2)), 3)

        rule_y = sub_y + sub.get_height() + 6
        pygame.draw.line(screen, (*accent, 150), (x, rule_y), (x + w * 0.42, rule_y), 1)
        pygame.draw.line(screen, (*accent, 45), (x + w * 0.42, rule_y), (x + w, rule_y), 1)
        return rule_y + 1

    def _draw_body_section(self, screen, x, y, w, h, accent, ctx):
        from effects_kit import draw_arc_segment
        import body_scan

        fig_h = int(h - 16)
        fig_w = int(fig_h * 0.52)
        fig_x = int(x + (w - fig_w) / 2)
        fig_y = int(y + 6)

        cx = fig_x + fig_w / 2.0
        torso_cy = fig_y + fig_h * 0.40
        # Tight enough to sit just outside the arms -- a ring floating far
        # off the body reads as decoration rather than instrumentation.
        ring_r = fig_h * 0.30

        # Static tick ring around the torso
        for i in range(60):
            ang = math.radians(i * 6)
            inner = ring_r + 6
            outer = inner + (6 if i % 5 == 0 else 3)
            a = 110 if i % 5 == 0 else 55
            pygame.draw.line(
                screen, (*accent, a),
                (cx + math.cos(ang) * inner, torso_cy + math.sin(ang) * inner),
                (cx + math.cos(ang) * outer, torso_cy + math.sin(ang) * outer), 1)

        # Two slow counter-rotating accent arcs
        t = pygame.time.get_ticks() / 1000.0
        spin = (t * 7.0) % 360
        for base, col, thick in ((spin, accent, 3), (-spin * 0.6 + 180, (255, 150, 70), 2)):
            draw_arc_segment(screen, cx, torso_cy, ring_r + 16, base, base + 54,
                             col, thickness=thick, alpha=200)
            draw_arc_segment(screen, cx, torso_cy, ring_r + 16, base + 180, base + 218,
                             col, thickness=thick, alpha=120)

        scan_frac = (t * 0.22) % 1.0
        bpm = ctx['bpm'] or 60.0
        beat_phase = (t * (bpm / 60.0)) % 1.0
        pulse = max(0.0, 1.0 - beat_phase * 4.0) ** 2

        body_scan.draw(screen, fig_x, fig_y, fig_w, fig_h, accent,
                       scan_frac, pulse=pulse, scan_color=(205, 245, 255))

        # Corner annotations
        scan_lbl = self._text('f_nano', "SCAN ACTIVE", accent, spacing=2)
        screen.blit(scan_lbl, (x, y + 4))
        for i in range(5):
            bar_x = x + i * 7
            lit = (int(t * 4) % 5) == i
            pygame.draw.line(screen, (*accent, 220 if lit else 70),
                             (bar_x, y + 18), (bar_x + 4, y + 18), 2)

        # Calibration scale beside the figure, with a marker riding the
        # scan head -- ties the sweep to a readable axis.
        sc_x = fig_x - 16
        for i in range(21):
            ty = fig_y + fig_h * i / 20.0
            major = (i % 5 == 0)
            pygame.draw.line(screen, (*accent, 105 if major else 42),
                             (sc_x - (8 if major else 4), ty), (sc_x, ty), 1)
        mk_y = fig_y + fig_h * scan_frac
        pygame.draw.polygon(screen, (*accent, 235), [
            (sc_x + 2, mk_y), (sc_x - 4, mk_y - 4), (sc_x - 4, mk_y + 4)])

        subj = self._text('f_micro', "SUBJECT 01", COLOR_TEXT_SECONDARY, spacing=2)
        screen.blit(subj, (x, y + h - 26))
        stat = self._text('f_micro', ctx['status_text'], ctx['status_color'], spacing=2)
        screen.blit(stat, (x, y + h - 13))

        # Leader lines from body nodes out to micro-labelled readouts
        heart_pt = body_scan.node_pos(fig_x, fig_y, fig_w, fig_h, body_scan.HEART_NODE)
        r_lbl = self._text('f_nano', "CARDIAC", COLOR_TEXT_DIM, spacing=1)
        r_val = self._text('f_small', ctx['hr_text'], COLOR_FONT_BODY)
        r_wide = max(r_lbl.get_width(), r_val.get_width())
        self._draw_leader(screen, heart_pt, x + w - 5 - r_wide, r_lbl, r_val,
                          accent, 'right')

        wrist_pt = body_scan.node_pos(fig_x, fig_y, fig_w, fig_h, body_scan.WRIST_NODE)
        mirrored_x = fig_x + fig_w - (wrist_pt[0] - fig_x)
        l_lbl = self._text('f_nano', "LOCOMOTION", COLOR_TEXT_DIM, spacing=1)
        l_val = self._text('f_small', ctx['steps_text'], COLOR_FONT_BODY)
        l_wide = max(l_lbl.get_width(), l_val.get_width())
        self._draw_leader(screen, (mirrored_x, wrist_pt[1]), x + 5 + l_wide,
                          l_lbl, l_val, accent, 'left')

    def _draw_cardio(self, screen, x, y, w, h, accent, ctx):
        from effects_kit import draw_chamfer_frame
        draw_chamfer_frame(screen, x, y, w, h, accent, alpha=55, cut=9)

        pad = 9
        lbl = self._text('f_nano', "CARDIOVASCULAR", accent, spacing=2)
        screen.blit(lbl, (x + pad, y + 6))
        tag = self._text('f_nano', "RESTING", COLOR_TEXT_DIM, spacing=2)
        screen.blit(tag, (x + w - pad - tag.get_width(), y + 6))

        bpm_text = ctx['hr_text'] if ctx['hr_text'] != 'N/A' else '--'
        bpm_surf = self._text('f_hero', bpm_text, COLOR_FONT_BODY)
        bpm_y = y + 18
        screen.blit(bpm_surf, (x + pad, bpm_y))
        unit = self._text('f_nano', "BPM", COLOR_TEXT_SECONDARY, spacing=1)
        screen.blit(unit, (x + pad + bpm_surf.get_width() + 4,
                           bpm_y + bpm_surf.get_height() - unit.get_height() - 6))

        ecg_x = x + pad + bpm_surf.get_width() + 30
        ecg_w = (x + w - pad) - ecg_x
        if ecg_w > 40:
            self._draw_ecg(screen, ecg_x, bpm_y + 2, ecg_w, h - 44,
                           (255, 146, 92), ctx['bpm'])

        stats = []
        for key, label in (('hr_min', 'MIN'), ('hr_avg', 'AVG'), ('hr_max', 'MAX')):
            val = self.data.get(key)
            stats.append(f"{label} {val if val not in (None, 'N/A') else '--'}")
        row = self._text('f_nano', "   ".join(stats), COLOR_TEXT_DIM, spacing=1)
        screen.blit(row, (x + w - pad - row.get_width(), y + h - row.get_height() - 6))

    def _draw_gauges(self, screen, x, y, w, h, accent, ctx):
        from effects_kit import draw_segmented_ring, draw_arc_segment

        r = int(min(h * 0.32, w * 0.135))
        cy = y + r + 14
        left_cx = x + r + 6
        right_cx = left_cx + r * 2 + 26

        # LOCOMOTION. The rings stay accent-coloured rather than going
        # traffic-light -- the status word carries the warning semantics,
        # so the instrument panel keeps one coherent palette.
        steps_color = accent
        draw_segmented_ring(screen, left_cx, cy, r, ctx['steps_frac'], steps_color,
                            segments=30, thickness=7)
        val = self._text('f_value', ctx['steps_text'], COLOR_FONT_BODY)
        screen.blit(val, (left_cx - val.get_width() // 2, cy - val.get_height() // 2 - 5))
        goal = self._text('f_nano', f"GOAL {ctx['step_goal']:,}", COLOR_TEXT_DIM)
        screen.blit(goal, (left_cx - goal.get_width() // 2, cy + 8))
        lbl = self._text('f_nano', "LOCOMOTION", accent, spacing=2)
        screen.blit(lbl, (left_cx - lbl.get_width() // 2, cy + r + 8))

        # RECOVERY
        rec_color = accent
        draw_segmented_ring(screen, right_cx, cy, r, ctx['readiness'], rec_color,
                            segments=30, thickness=7)
        spin = (pygame.time.get_ticks() / 1000.0 * 22.0) % 360
        draw_arc_segment(screen, right_cx, cy, r + 9, spin, spin + 36,
                         accent, thickness=2, alpha=190)
        pct = self._text('f_value', f"{int(ctx['readiness'] * 100)}%", COLOR_FONT_BODY)
        screen.blit(pct, (right_cx - pct.get_width() // 2, cy - pct.get_height() // 2 - 5))
        sub = self._text('f_nano', "INDEX", COLOR_TEXT_DIM)
        screen.blit(sub, (right_cx - sub.get_width() // 2, cy + 8))
        lbl2 = self._text('f_nano', "RECOVERY", accent, spacing=2)
        screen.blit(lbl2, (right_cx - lbl2.get_width() // 2, cy + r + 8))

        # Supporting readouts
        sx = right_cx + r + 16
        sw = (x + w) - sx
        if sw > 60:
            rows = [
                ("ENERGY EXPENDITURE", ctx['calories_text'], "KCAL"),
                ("DISTANCE", ctx['distance_text'], "KM"),
                ("ACTIVE", ctx['active_text'], "MIN"),
            ]
            ry = y + 12
            for label, value, unit in rows:
                l = self._text('f_nano', label, COLOR_TEXT_DIM, spacing=1)
                screen.blit(l, (sx, ry))
                v = self._text('f_small', value, COLOR_FONT_BODY)
                screen.blit(v, (sx, ry + l.get_height() + 1))
                u = self._text('f_nano', unit, COLOR_TEXT_SECONDARY)
                screen.blit(u, (sx + v.get_width() + 4,
                                ry + l.get_height() + v.get_height() - u.get_height() - 1))
                pygame.draw.line(screen, (*accent, 40),
                                 (sx, ry + l.get_height() + v.get_height() + 4),
                                 (sx + sw - 4, ry + l.get_height() + v.get_height() + 4), 1)
                ry += l.get_height() + v.get_height() + 12

    def _draw_sleep(self, screen, x, y, w, h, accent, ctx):
        from effects_kit import draw_chamfer_frame
        draw_chamfer_frame(screen, x, y, w, h, accent, alpha=55, cut=9)
        pad = 9

        lbl = self._text('f_nano', "SLEEP CYCLE", accent, spacing=2)
        screen.blit(lbl, (x + pad, y + 6))
        dur = self._text('f_small', ctx['sleep_label'], COLOR_FONT_BODY)
        screen.blit(dur, (x + w - pad - dur.get_width(), y + 4))

        bar_x = x + pad
        bar_w = w - pad * 2
        bar_y = y + 22
        bar_h = 14
        stages = ctx['sleep_stages']
        if stages:
            total = sum(secs for _, secs in stages) or 1
            px = float(bar_x)
            for level, secs in stages:
                seg_w = bar_w * (secs / total)
                color = self.STAGE_COLORS.get(level, self.STAGE_COLORS['light'])
                pygame.draw.rect(screen, (*color, 225),
                                 (int(px), bar_y, max(1, int(seg_w + 0.5)), bar_h))
                px += seg_w
        else:
            frac = ctx['sleep_frac']
            pygame.draw.rect(screen, (*accent, 40), (bar_x, bar_y, bar_w, bar_h))
            pygame.draw.rect(screen, (*accent, 210),
                             (bar_x, bar_y, int(bar_w * frac), bar_h))
        pygame.draw.rect(screen, (*accent, 90), (bar_x, bar_y, bar_w, bar_h), 1)

        start = ctx['sleep_start'] or ''
        end = ctx['sleep_end'] or ''
        if start:
            screen.blit(self._text('f_nano', start, COLOR_TEXT_DIM), (bar_x, bar_y + bar_h + 3))
        if end:
            es = self._text('f_nano', end, COLOR_TEXT_DIM)
            screen.blit(es, (bar_x + bar_w - es.get_width(), bar_y + bar_h + 3))

        # Legend for the stages actually present
        present = []
        for level, _ in stages:
            if level not in present:
                present.append(level)
        lx = bar_x
        ly = bar_y + bar_h + 16
        for level in present[:4]:
            color = self.STAGE_COLORS.get(level, self.STAGE_COLORS['light'])
            pygame.draw.circle(screen, (*color, 235), (int(lx), int(ly + 4)), 3)
            t = self._text('f_nano', level.upper(), COLOR_TEXT_DIM, spacing=1)
            screen.blit(t, (lx + 7, ly))
            lx += 7 + t.get_width() + 12

    def _draw_weekly(self, screen, x, y, w, h, accent, ctx):
        from effects_kit import draw_chamfer_frame
        draw_chamfer_frame(screen, x, y, w, h, accent, alpha=55, cut=9)
        pad = 9

        lbl = self._text('f_nano', "ACTIVITY  7 DAY", accent, spacing=2)
        screen.blit(lbl, (x + pad, y + 6))

        weekly = ctx['weekly']
        if weekly:
            avg = int(sum(v for _, v in weekly) / len(weekly))
            stat = self._text('f_nano', f"AVG {avg:,}", COLOR_TEXT_SECONDARY, spacing=1)
            screen.blit(stat, (x + w - pad - stat.get_width(), y + 6))

        plot_y = y + 20
        plot_h = h - 36
        bar_area_x = x + pad
        bar_area_w = w - pad * 2
        if not weekly or plot_h < 12:
            none_lbl = self._text('f_nano', "AWAITING SYNC", COLOR_TEXT_DIM, spacing=1)
            screen.blit(none_lbl, (x + w // 2 - none_lbl.get_width() // 2, plot_y + 8))
            return

        peak = max(max(v for _, v in weekly), ctx['step_goal'])
        slot = bar_area_w / len(weekly)
        bar_w = max(5, int(slot * 0.5))
        goal_y = plot_y + plot_h - plot_h * (ctx['step_goal'] / peak)
        pygame.draw.line(screen, (*accent, 70), (bar_area_x, goal_y),
                         (bar_area_x + bar_area_w, goal_y), 1)

        today = datetime.now().strftime("%Y-%m-%d")
        for i, (date_str, value) in enumerate(weekly):
            bar_h = max(1, int(plot_h * (value / peak)))
            bx = int(bar_area_x + slot * i + (slot - bar_w) / 2)
            by = int(plot_y + plot_h - bar_h)
            is_today = date_str == today
            color = accent if is_today else (110, 150, 180)
            pygame.draw.rect(screen, (*color, 235 if is_today else 150),
                             (bx, by, bar_w, bar_h))
            try:
                letter = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a")[0]
            except ValueError:
                letter = "-"
            ds = self._text('f_nano', letter,
                            COLOR_TEXT_SECONDARY if is_today else COLOR_TEXT_DIM)
            screen.blit(ds, (bx + bar_w // 2 - ds.get_width() // 2, plot_y + plot_h + 3))

    def _draw_footer(self, screen, x, y, w, accent):
        from effects_kit import draw_tick_scale
        draw_tick_scale(screen, x, y, w * 0.55, accent, count=22, major_every=5, alpha=90)
        if self.last_update:
            mins = int((datetime.now() - self.last_update).total_seconds() // 60)
            text = f"SYNCED {mins}M AGO" if mins else "SYNCED JUST NOW"
        else:
            text = "AWAITING LINK"
        s = self._text('f_nano', text, COLOR_TEXT_DIM, spacing=1)
        screen.blit(s, (x + w - s.get_width(), y))

    def _build_context(self):
        """Everything the renderer needs, resolved from real data once."""
        step_goal = 10000
        if 'goals' in self.data and 'steps' in self.data['goals']:
            step_goal = int(self.data['goals']['steps'])
        try:
            steps_int = int(self.data.get('steps', 0))
        except (TypeError, ValueError):
            steps_int = 0
        steps_frac = min(1.0, steps_int / step_goal) if step_goal else 0.0

        sleep_text = self.data.get('sleep')
        sleep_hours = None
        if sleep_text not in (None, 'N/A') and ':' in str(sleep_text):
            try:
                h, m = str(sleep_text).split(':')
                sleep_hours = int(h) + int(m) / 60.0
            except ValueError:
                sleep_hours = None
        sleep_frac = min(1.0, (sleep_hours or 0) / 8.0)
        if sleep_hours is not None:
            sleep_label = f"{int(sleep_hours)}h {int(round((sleep_hours % 1) * 60)):02d}m"
        else:
            sleep_label = "--"

        hr = self.data.get('resting_heart_rate')
        try:
            bpm = float(hr)
        except (TypeError, ValueError):
            bpm = None

        readiness = self._readiness_fraction(steps_frac, sleep_frac, hr)
        status_text, status_color = self._status(readiness, hr)

        def fmt(value, digits=0):
            try:
                num = float(value)
            except (TypeError, ValueError):
                return "--"
            return f"{num:,.{digits}f}"

        return {
            'step_goal': step_goal,
            'steps_frac': steps_frac,
            'steps_text': f"{steps_int:,}",
            'sleep_frac': sleep_frac,
            'sleep_label': sleep_label,
            'sleep_stages': self.data.get('sleep_stages') or [],
            'sleep_start': self.data.get('sleep_start'),
            'sleep_end': self.data.get('sleep_end'),
            'hr_text': str(hr) if hr not in (None, 'N/A') else 'N/A',
            'bpm': bpm,
            'readiness': readiness,
            'status_text': status_text,
            'status_color': status_color,
            'calories_text': fmt(self.data.get('calories')),
            'distance_text': fmt(self.data.get('distance'), 1),
            'active_text': fmt(self.data.get('active_minutes')),
            'weekly': self.data.get('weekly_steps') or [],
        }

    def draw(self, screen, position):
        """BIOMETRIC MONITOR: a habitat vital-signs station.

        A scanned anatomical figure anchors the composition; ECG,
        segmented gauges, a real sleep-stage timeline and a 7-day activity
        graph read off it. Every value is real Fitbit data -- the only
        things running on a fixed cycle are the scan sweep and the ambient
        arcs. Not a stack of cards (see AI-Mirror.py's NO_PANEL_FRAME);
        the chamfered console frames and the figure carry the structure.
        """
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 200)
            else:
                x, y = position
                width, height = 300, 200

            self._ensure_fonts()

            # Everything composites through one reusable alpha layer.
            # pygame.draw.* ignores the alpha channel of its colour when it
            # writes straight to the display surface, so drawn-on-screen
            # "faint" elements (gauge tracks, ECG grid ruling, scale ticks)
            # would otherwise all render at full brightness -- which flattens
            # a segmented gauge into a solid ring showing no value at all.
            # Drawing into an SRCALPHA layer and blitting it once makes every
            # alpha meaningful, for one allocation per module size.
            layer = self._get_layer(width, height)
            layer.fill((0, 0, 0, 0))
            self._render(layer, width, height)
            screen.blit(layer, (x, y))

        except Exception as e:
            logging.error(f"Error drawing Fitbit data: {e}")
            logging.error(traceback.format_exc())

    def _get_layer(self, width, height):
        layer = getattr(self, '_layer', None)
        if layer is None or layer.get_size() != (width, height):
            layer = pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)
            self._layer = layer
        return layer

    def _render(self, surf, width, height):
        """Draw the whole composition in layer-local coordinates."""
        import theme
        accent = theme.module_accent('fitbit')

        pad = 8
        ix = pad
        iw = width - pad * 2

        if self._api_retired:
            msg = self._text('f_value', "BIOMETRIC LINK OFFLINE", COLOR_ACCENT_AMBER)
            surf.blit(msg, (ix, 20))
            sub = self._text('f_nano', "FITBIT LEGACY API RETIRED", COLOR_TEXT_DIM, spacing=2)
            surf.blit(sub, (ix, 20 + msg.get_height() + 4))
            return
        if not self.data:
            msg = self._text('f_value', "ACQUIRING SUBJECT...", COLOR_TEXT_SECONDARY)
            surf.blit(msg, (ix, 20))
            return

        ctx = self._build_context()

        gap = 6
        head_h = 46
        foot_h = 14
        flex = height - head_h - foot_h - gap * 5
        if flex < 160:
            return
        body_h = int(flex * 0.360)
        cardio_h = int(flex * 0.145)
        gauge_h = int(flex * 0.225)
        sleep_h = int(flex * 0.135)
        week_h = flex - body_h - cardio_h - gauge_h - sleep_h

        cur = 0
        self._draw_header(surf, ix, cur, iw, accent,
                          ctx['status_text'], ctx['status_color'])
        cur += head_h + gap
        self._draw_body_section(surf, ix, cur, iw, body_h, accent, ctx)
        cur += body_h + gap
        self._draw_cardio(surf, ix, cur, iw, cardio_h, accent, ctx)
        cur += cardio_h + gap
        self._draw_gauges(surf, ix, cur, iw, gauge_h, accent, ctx)
        cur += gauge_h + gap
        self._draw_sleep(surf, ix, cur, iw, sleep_h, accent, ctx)
        cur += sleep_h + gap
        self._draw_weekly(surf, ix, cur, iw, week_h, accent, ctx)
        cur += week_h + gap
        self._draw_footer(surf, ix, cur, iw, accent)

    def cleanup(self):
        pass