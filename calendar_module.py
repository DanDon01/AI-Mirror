from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
import datetime
import logging
import pygame
import os
from dotenv import load_dotenv
import traceback
from api_tracker import api_tracker
from google_auth_oauthlib.flow import Flow
from config import FONT_NAME, COLOR_FONT_DEFAULT, COLOR_FONT_BODY, COLOR_PASTEL_RED, TRANSPARENCY, CONFIG, COLOR_TEXT_DIM, COLOR_TEXT_SECONDARY, COLOR_ACCENT_PURPLE
from background_fetcher import BackgroundFetcher
from effects_kit import draw_flare
from module_base import FLARE_DURATION_S, InstrumentPanel
import time

# Google Calendar color mapping - these match the standard Google Calendar colors
GOOGLE_CALENDAR_COLORS = {
    '1': (166, 118, 242),  # Lavender
    '2': (120, 147, 255),  # Sage
    '3': (102, 178, 226),  # Grape
    '4': (82, 183, 189),   # Flamingo
    '5': (103, 192, 163),  # Banana
    '6': (118, 198, 124),  # Tangerine
    '7': (194, 151, 104),  # Peacock
    '8': (206, 129, 116),  # Graphite
    '9': (150, 133, 164),  # Blueberry
    '10': (205, 133, 134), # Basil
    '11': (225, 181, 180)  # Tomato
}

# Default colors for calendar events
DEFAULT_CALENDAR_COLORS = [
    (120, 180, 240),  # Blue
    (120, 200, 120),  # Green
    (240, 180, 120),  # Orange
    (200, 120, 200),  # Purple
    (240, 140, 140)   # Red
]

class CalendarModule(InstrumentPanel):
    def __init__(self, config):
        self.SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        self.config = config
        self.events = []
        self.font = None
        self.last_update = datetime.datetime.min
        self.update_interval = datetime.timedelta(hours=1)  # Update every hour
        self.service = None
        self.last_error = None
        self.last_fetch_started = None
        self.env_file = os.path.join(os.path.dirname(__file__), '..', 'Variables.env')
        self.load_tokens()

        self.last_update_time = time.time()
        self.today_highlight_color = (0, 40, 80, 120)
        self.color_map = None
        self._fetcher = BackgroundFetcher("calendar")
        self._events_key = None
        self._events_changed_at = None

        # Show last-good events immediately after a restart
        from data_cache import data_cache
        cached, age = data_cache.load("calendar", max_age_sec=86400)
        if cached:
            self.events = cached
            logging.info(f"Restored {len(self.events)} cached calendar events "
                         f"({int(age / 60)} min old)")

    def load_tokens(self):
        load_dotenv(self.env_file)
        # Keep values supplied by the caller when Variables.env is absent or
        # incomplete.  The old pygame path often passed a complete config;
        # replacing it with four Nones made the visual bridge look unconfigured.
        for key, env_name in (
            ('client_id', 'GOOGLE_CLIENT_ID'),
            ('client_secret', 'GOOGLE_CLIENT_SECRET'),
            ('access_token', 'GOOGLE_ACCESS_TOKEN'),
            ('refresh_token', 'GOOGLE_REFRESH_TOKEN'),
        ):
            value = os.getenv(env_name)
            if value:
                self.config[key] = value

    def save_tokens(self, creds):
        self.config['access_token'] = creds.token
        self.config['refresh_token'] = creds.refresh_token
        
        with open(self.env_file, 'r') as file:
            lines = file.readlines()
        
        with open(self.env_file, 'w') as file:
            for line in lines:
                if line.startswith('GOOGLE_ACCESS_TOKEN='):
                    file.write(f"GOOGLE_ACCESS_TOKEN={creds.token}\n")
                elif line.startswith('GOOGLE_REFRESH_TOKEN='):
                    file.write(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}\n")
                else:
                    file.write(line)

        logging.info("Google Calendar tokens have been saved to environment file")

    def get_credentials(self):
        creds = Credentials(
            token=self.config.get('access_token'),
            refresh_token=self.config.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.config.get('client_id'),
            client_secret=self.config.get('client_secret'),
            scopes=self.SCOPES
        )

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self.save_tokens(creds)
                    logging.info("Credentials refreshed successfully")
                except RefreshError:
                    logging.error("Failed to refresh token. Manual re-authentication may be required.")
                    return None
            else:
                logging.error("Credentials are invalid and cannot be refreshed. Manual re-authentication is required.")
                return None

        return creds

    def build_service(self):
        if not self.service:
            creds = self.get_credentials()
            if creds:
                self.service = build('calendar', 'v3', credentials=creds)
                logging.info("Google Calendar service built successfully.")
            else:
                logging.error("Failed to build Google Calendar service due to invalid credentials.")

    def _fetch_events_blocking(self):
        """Token refresh + Google API round-trips. Runs on a background
        thread because each call is a 1-3 second network round-trip.

        Returns (events, color_map_or_None).
        """
        try:
            self.build_service()
            if not self.service:
                raise RuntimeError("Calendar service unavailable (credentials?)")

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Calendar colors never change mid-session: fetch once
            color_map = None
            if self.color_map is None:
                colors = self.service.colors().get().execute()
                color_map = colors['event']

            events_result = self.service.events().list(calendarId='primary', timeMin=now,
                                                       maxResults=10, singleEvents=True,
                                                       orderBy='startTime').execute()
            api_tracker.record("calendar", "google-calendar")
            return events_result.get('items', []), color_map
        except Exception:
            api_tracker.failure("calendar", "google-calendar")
            raise

    def update(self):
        result = self._fetcher.take_result()
        if result is not None:
            ok, value = result
            if ok:
                events, color_map = value
                self.events = events
                if color_map:
                    self.color_map = color_map
                from data_cache import data_cache
                data_cache.save("calendar", self.events)
                logging.info(f"Calendar updated: {len(self.events)} events")
                self.last_error = None

                # "Calm for static, flare on change": a brief highlight the
                # instant the event list actually differs, not on every
                # routine refresh that comes back unchanged.
                key = tuple(e.get('id', e.get('summary', '')) for e in self.events)
                if self._events_key is not None and key != self._events_key:
                    self._events_changed_at = time.time()
                self._events_key = key
            else:
                logging.error(f"Error updating Calendar data: {value}")
                self.last_error = str(value)
                # Keep showing the previous events rather than blanking
            self.last_update = datetime.datetime.now()

        current_time = datetime.datetime.now()
        if current_time - self.last_update < self.update_interval:
            return
        if not api_tracker.allow("calendar", "google-calendar"):
            return
        if self._fetcher.submit(self._fetch_events_blocking):
            self.last_fetch_started = time.time()

    def force_refresh(self):
        """Queue a calendar refresh immediately, without blocking the UI."""
        self.last_update = datetime.datetime.min
        self.update()
        return not self._fetcher.idle

    def parsed_events(self, limit=7):
        """Events resolved to real datetimes, soonest first."""
        out = []
        now = datetime.datetime.now()
        for event in self.events or []:
            start = event.get('start', {})
            when, all_day = None, False
            if 'dateTime' in start:
                try:
                    when = datetime.datetime.fromisoformat(
                        str(start['dateTime']).replace('Z', '+00:00'))
                    when = when.astimezone().replace(tzinfo=None)
                except (TypeError, ValueError):
                    when = None
            elif 'date' in start:
                try:
                    when = datetime.datetime.fromisoformat(str(start['date']))
                    all_day = True
                except (TypeError, ValueError):
                    when = None
            if when is None:
                continue
            out.append({
                'when': when,
                'all_day': all_day,
                'summary': event.get('summary', 'No title'),
                'color': self.get_event_color(event),
                'delta': when - now,
            })
        out.sort(key=lambda e: e['when'])
        return out[:limit]

    @staticmethod
    def _day_chip(when, now):
        days = (when.date() - now.date()).days
        if days == 0:
            return "TODAY"
        if days == 1:
            return "TOMORROW"
        if days < 7:
            return when.strftime("%A").upper()
        return when.strftime("%a %d %b").upper()

    @staticmethod
    def _countdown_label(delta):
        seconds = delta.total_seconds()
        if seconds < 0:
            return "NOW"
        if seconds < 3600:
            return f"IN {int(seconds // 60)}M"
        if seconds < 86400:
            return f"IN {int(seconds // 3600)}H"
        return f"IN {int(seconds // 86400)}D"

    def draw(self, screen, position):
        """SCHEDULE: the calendar as a timeline rail."""
        self.draw_instrument(screen, position, default=(300, 300))

    def _render_panel(self, surf, width, height, position=None):
        import theme
        accent = theme.module_accent('calendar')
        pad = 6
        ix, iw = pad, width - pad * 2

        events = self.parsed_events(7)
        cur = self._panel_header(
            surf, ix, 0, iw, "Schedule", accent,
            subtitle=datetime.datetime.now().strftime("%a %d %B").upper(),
            right_text=f"{len(events)} LOGGED" if events else None)

        if not events:
            msg = self._text('f_small', "NO EVENTS SCHEDULED",
                             COLOR_TEXT_SECONDARY, spacing=1)
            surf.blit(msg, (ix, cur + 8))
            return

        rail_x = ix + 16
        now = datetime.datetime.now()

        # "NOW" origin marker at the top of the rail
        pygame.draw.circle(surf, (255, 255, 255, 235), (int(rail_x), int(cur + 5)), 3)
        now_lbl = self._text('f_nano', "NOW", COLOR_TEXT_SECONDARY, spacing=2)
        surf.blit(now_lbl, (rail_x + 12, cur))
        time_lbl = self._text('f_nano', now.strftime("%H:%M"), COLOR_TEXT_DIM, spacing=1)
        surf.blit(time_lbl, (ix + iw - time_lbl.get_width(), cur))
        cur += 14

        last_chip = None
        rail_top = cur
        rail_bottom = cur
        for item in events:
            if cur + 34 > height:
                break

            chip = self._day_chip(item['when'], now)
            if chip != last_chip:
                if cur + 48 > height:
                    break
                cs = self._text('f_nano', chip, accent, spacing=2)
                surf.blit(cs, (rail_x + 12, cur))
                pygame.draw.line(surf, (*accent, 45),
                                 (rail_x + 16 + cs.get_width(), cur + cs.get_height() / 2),
                                 (ix + iw, cur + cs.get_height() / 2), 1)
                cur += cs.get_height() + 5
                last_chip = chip

            node_y = cur + 9
            pygame.draw.circle(surf, (*item['color'], 70), (int(rail_x), int(node_y)), 6)
            pygame.draw.circle(surf, (*item['color'], 245), (int(rail_x), int(node_y)), 3)
            pygame.draw.line(surf, (*item['color'], 120),
                             (rail_x + 6, node_y), (rail_x + 12, node_y), 1)

            when_text = "ALL DAY" if item['all_day'] else item['when'].strftime("%H:%M")
            wt = self._text('f_small', when_text, COLOR_FONT_BODY)
            surf.blit(wt, (rail_x + 16, cur))
            cd = self._text('f_nano', self._countdown_label(item['delta']),
                            COLOR_TEXT_DIM, spacing=1)
            surf.blit(cd, (ix + iw - cd.get_width(), cur + 3))

            title = item['summary']
            max_chars = max(14, int((iw - 26) / 5.6))
            if len(title) > max_chars:
                title = title[:max_chars - 2].rstrip() + ".."
            ts = self._text('f_nano', title.upper(), item['color'], spacing=1)
            surf.blit(ts, (rail_x + 16, cur + wt.get_height() - 1))

            rail_bottom = node_y
            cur += 32

        pygame.draw.line(surf, (*accent, 55), (rail_x, rail_top),
                         (rail_x, rail_bottom), 1)

    def get_event_color(self, event):
        """Get the color for an event based on Google Calendar color scheme"""
        # Check if event has a specific color ID
        if 'colorId' in event:
            color_id = event['colorId']
            if color_id in GOOGLE_CALENDAR_COLORS:
                return GOOGLE_CALENDAR_COLORS[color_id]
        
        # If we have color information from the API
        if self.color_map and 'colorId' in event:
            color_id = event['colorId']
            if color_id in self.color_map:
                color_hex = self.color_map[color_id].get('background', '#4285F4')
                # Convert hex to RGB
                try:
                    r = int(color_hex[1:3], 16)
                    g = int(color_hex[3:5], 16)
                    b = int(color_hex[5:7], 16)
                    return (r, g, b)
                except Exception:
                    pass
        
        # Fallback to using a hash of the calendar ID for consistent colors
        if 'organizer' in event and 'email' in event['organizer']:
            email = event['organizer']['email']
            hash_value = sum(ord(c) for c in email) % len(DEFAULT_CALENDAR_COLORS)
            return DEFAULT_CALENDAR_COLORS[hash_value]
        
        # Final fallback to default blue
        return DEFAULT_CALENDAR_COLORS[0]

    def test(self):
        pygame.init()
        screen = pygame.display.set_mode((800, 600))
        clock = pygame.time.Clock()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            screen.fill((0, 0, 0))  # Black background
            
            self.update()
            self.draw(screen, (10, 10))  # Draw at position (10, 10)

            pygame.display.flip()
            clock.tick(30)  # 30 FPS

        pygame.quit()

    def cleanup(self):
        pass  # No specific cleanup needed for this module

# Test code
# if __name__ == "__main__":
#    from config import CONFIG  # Make sure to import your config
#    calendar_module = CalendarModule(CONFIG)
#    calendar_module.test()
