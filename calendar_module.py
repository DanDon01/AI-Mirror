from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import datetime
import logging
import pygame
import os
from dotenv import load_dotenv
import traceback
from google_auth_oauthlib.flow import Flow
from config import FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_PASTEL_RED, LINE_SPACING, TRANSPARENCY

class CalendarModule:
    def __init__(self, config):
        self.SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        self.config = config
        self.events = []
        self.font = None
        self.last_update = datetime.datetime.min
        self.update_interval = datetime.timedelta(hours=24)  # Update daily
        self.service = None
        self.env_file = os.path.join(os.path.dirname(__file__), '..', 'Variables.env')
        load_dotenv(self.env_file)
        self.color_map = {}  # To store calendar color information

    def authenticate(self):
        creds = Credentials(
            token=self.config.get('access_token'),
            refresh_token=self.config.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.config.get('client_id'),
            client_secret=self.config.get('client_secret'),
            scopes=self.SCOPES
        )

        if not creds.valid:
            logging.info("Credentials are not valid.")
            if creds.expired and creds.refresh_token:
                try:
                    logging.info("Refreshing expired token...")
                    creds.refresh(Request())
                    logging.info("Token successfully refreshed.")
                except Exception as e:
                    logging.error(f"Error refreshing token: {e}")
                    logging.info("Attempting re-authentication...")
                    creds = self.reauth()
            else:
                logging.info("Credentials are invalid or refresh token not available. Re-authenticating...")
                creds = self.reauth()

        self.save_tokens(creds)
        return creds

    def reauth(self):
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.config.get('client_id'),
                    "client_secret": self.config.get('client_secret'),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            },
            scopes=self.SCOPES
        )
        flow.run_local_server(port=0)
        creds = flow.credentials
        self.save_tokens(creds)
        return creds

    def save_tokens(self, creds):
        self.config['access_token'] = creds.token
        self.config['refresh_token'] = creds.refresh_token
        
        env_file = os.path.join(os.path.dirname(__file__), '..', 'Variables.env')
        with open(env_file, 'r') as file:
            lines = file.readlines()
        
        with open(env_file, 'w') as file:
            for line in lines:
                if line.startswith('GOOGLE_ACCESS_TOKEN='):
                    file.write(f"GOOGLE_ACCESS_TOKEN={creds.token}\n")
                elif line.startswith('GOOGLE_REFRESH_TOKEN='):
                    file.write(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}\n")
                else:
                    file.write(line)

        logging.info("Google Calendar tokens have been saved to environment file")

    def build_service(self):
        if not self.service:
            creds = self.authenticate()
            self.service = build('calendar', 'v3', credentials=creds)
            logging.info("Google Calendar service built successfully.")

    def update(self):
        current_time = datetime.datetime.now()
        if current_time - self.last_update < self.update_interval:
            logging.info("Skipping update: Not enough time has passed since last update.")
            return  # Skip update if not enough time has passed

        try:
            self.build_service()
            now = current_time.isoformat() + 'Z'  # 'Z' indicates UTC time
            logging.debug(f"Requesting events starting from: {now}")
            
            # Fetch calendar color information
            colors = self.service.colors().get().execute()
            self.color_map = colors['event']

            events_result = self.service.events().list(calendarId='primary', timeMin=now,
                                                       maxResults=10, singleEvents=True,
                                                       orderBy='startTime').execute()
            self.events = events_result.get('items', [])
            self.last_update = current_time
            logging.info(f"Successfully updated calendar events. Number of events fetched: {len(self.events)}")
        except Exception as e:
            logging.error(f"Error updating Calendar data: {e}")
            logging.error(traceback.format_exc())
            self.events = None  # Indicate that an error occurred

    def draw(self, screen, position):
        if self.font is None:
            try:
                self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE)
            except:
                print(f"Warning: Font '{FONT_NAME}' not found. Using default font.")
                self.font = pygame.font.Font(None, FONT_SIZE)  # Fallback to default font
        
        x, y = position
        if self.events is None:
            error_surface = self.font.render("Calendar Error", True, COLOR_PASTEL_RED)
            error_surface.set_alpha(TRANSPARENCY)
            screen.blit(error_surface, (x, y))
            return

        today = datetime.date.today()
        y_offset = 0
        for event in self.events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            if 'T' in start:  # This is a datetime
                start_date = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                time_str = start_date.strftime("%H:%M")
            else:  # This is a date
                start_date = datetime.date.fromisoformat(start)
                time_str = "All day"
            
            if isinstance(start_date, datetime.datetime):
                start_date = start_date.date()
            
            if start_date < today:
                continue  # Skip past events
            
            if start_date > today + datetime.timedelta(days=7):
                break  # Don't show events more than a week in the future
            
            day_name = start_date.strftime("%a")
            date_str = start_date.strftime("%d/%m")  # UK date format
            event_summary = event['summary'] if len(event['summary']) <= 15 else event['summary'][:12] + "..."
            
            event_text = f"{day_name} {date_str} {time_str}: {event_summary}"

            # Get event color
            color_id = event.get('colorId')
            if color_id and color_id in self.color_map:
                color = self.color_map[color_id]['background']
                event_color = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))  # Convert hex to RGB
            else:
                event_color = COLOR_FONT_DEFAULT

            event_surface = self.font.render(event_text, True, event_color)
            event_surface.set_alpha(TRANSPARENCY)
            screen.blit(event_surface, (x, y + y_offset))
            y_offset += LINE_SPACING

        if y_offset == 0:
            no_events_surface = self.font.render("No upcoming events", True, COLOR_FONT_DEFAULT)
            no_events_surface.set_alpha(TRANSPARENCY)
            screen.blit(no_events_surface, (x, y))

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
