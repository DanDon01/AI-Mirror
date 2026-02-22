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
from config import FONT_NAME, COLOR_FONT_DEFAULT, COLOR_PASTEL_RED, TRANSPARENCY, CONFIG, COLOR_TEXT_DIM, COLOR_TEXT_SECONDARY
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

class CalendarModule:
    def __init__(self, config):
        self.SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        self.config = config
        self.events = []
        self.font = None
        self.last_update = datetime.datetime.min
        self.update_interval = datetime.timedelta(hours=1)  # Update every hour
        self.service = None
        self.env_file = os.path.join(os.path.dirname(__file__), '..', 'Variables.env')
        self.load_tokens()
        
        self.last_update_time = time.time()
        self.today_highlight_color = (0, 40, 80, 120)

    def load_tokens(self):
        load_dotenv(self.env_file)
        self.config['client_id'] = os.getenv('GOOGLE_CLIENT_ID')
        self.config['client_secret'] = os.getenv('GOOGLE_CLIENT_SECRET')
        self.config['access_token'] = os.getenv('GOOGLE_ACCESS_TOKEN')
        self.config['refresh_token'] = os.getenv('GOOGLE_REFRESH_TOKEN')

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

    def update(self):
        current_time = datetime.datetime.now()
        if current_time - self.last_update < self.update_interval:
            return  # Skip update if not enough time has passed

        try:
            if not api_tracker.allow("calendar", "google-calendar"):
                return
            self.build_service()
            if not self.service:
                logging.error("Calendar service is not available. Skipping update.")
                self.events = None
                return

            now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time

            # Fetch calendar color information
            colors = self.service.colors().get().execute()
            self.color_map = colors['event']

            events_result = self.service.events().list(calendarId='primary', timeMin=now,
                                                       maxResults=10, singleEvents=True,
                                                       orderBy='startTime').execute()
            api_tracker.record("calendar", "google-calendar")
            self.events = events_result.get('items', [])
            logging.info(f"Successfully updated calendar events. Number of events fetched: {len(self.events)}")
            self.last_update = current_time
        except Exception as e:
            logging.error(f"Error updating Calendar data: {e}")
            logging.error(traceback.format_exc())
            self.events = None

    def draw(self, screen, position):
        """Draw calendar with floating text on black -- no background."""
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 300)
            else:
                x, y = position
                width, height = 300, 300

            styling = CONFIG.get('module_styling', {})
            line_height = styling.get('spacing', {}).get('line_height', 28)

            if not self.font:
                from module_base import ModuleDrawHelper
                title_f, body_f, small_f = ModuleDrawHelper.get_fonts()
                self.title_font = title_f
                self.font = body_f
                self.small_font = small_f

            from module_base import ModuleDrawHelper
            current_y = ModuleDrawHelper.draw_module_title(
                screen, "Calendar", x, y, width
            )
            
            if not self.events:
                debug_text = self.font.render("No calendar events", True, COLOR_TEXT_SECONDARY)
                debug_text.set_alpha(TRANSPARENCY)
                screen.blit(debug_text, (x, current_y))
                return
            
            for event in self.events[:6]:
                if current_y > y + height - line_height:
                    break
                try:
                    event_color = self.get_event_color(event)

                    # Check if event is today
                    is_today = False
                    start = event.get('start', {})
                    if 'dateTime' in start:
                        try:
                            dt = datetime.datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                            is_today = dt.date() == datetime.datetime.now().date()
                        except Exception:
                            pass
                    elif 'date' in start:
                        try:
                            dt = datetime.datetime.fromisoformat(start['date'])
                            is_today = dt.date() == datetime.datetime.now().date()
                        except Exception:
                            pass

                    # Subtle highlight for today's events
                    if is_today:
                        today_surf = pygame.Surface((width, 36), pygame.SRCALPHA)
                        today_surf.fill(self.today_highlight_color)
                        screen.blit(today_surf, (x, current_y))

                    # Thin color indicator bar
                    pygame.draw.rect(screen, event_color, (x, current_y + 2, 3, 22))

                    # Format start time/date
                    start = event.get('start', {})
                    if 'dateTime' in start:
                        try:
                            dt = datetime.datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                            date_str = dt.strftime('%a %H:%M')
                        except Exception:
                            date_str = start['dateTime'][:16].replace('T', ' ')
                    else:
                        date_str = "All day"

                    date_surface = self.small_font.render(date_str, True, COLOR_TEXT_DIM)
                    date_surface.set_alpha(TRANSPARENCY)
                    screen.blit(date_surface, (x + 10, current_y))

                    # Event title
                    title = event.get('summary', 'No title')
                    max_chars = max(20, (width - 15) // 8)
                    if len(title) > max_chars:
                        title = title[:max_chars - 3] + "..."
                    title_surface = self.font.render(title, True, event_color)
                    title_surface.set_alpha(TRANSPARENCY)
                    screen.blit(title_surface, (x + 10, current_y + 16))

                    current_y += 38

                except Exception as e:
                    logging.error(f"Error drawing event: {e}")
                    current_y += 28
        
        except Exception as e:
            logging.error(f"Error drawing calendar: {e}")
            logging.error(traceback.format_exc())
            
            # Draw error message
            try:
                error_font = pygame.font.Font(None, 24)
                error_text = error_font.render("Calendar Error", True, (255, 50, 50))
                screen.blit(error_text, (x + 10, y + 10))
            except Exception:
                pass  # Last resort - if even error display fails

    def get_event_color(self, event):
        """Get the color for an event based on Google Calendar color scheme"""
        # Check if event has a specific color ID
        if 'colorId' in event:
            color_id = event['colorId']
            if color_id in GOOGLE_CALENDAR_COLORS:
                return GOOGLE_CALENDAR_COLORS[color_id]
        
        # If we have color information from the API
        if hasattr(self, 'color_map') and 'colorId' in event:
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
