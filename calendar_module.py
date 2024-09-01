from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import datetime
import logging
import pygame
import os
from dotenv import load_dotenv
import traceback

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

    def authenticate(self):
        creds = Credentials(
            token=self.config['access_token'],
            refresh_token=self.config['refresh_token'],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.config['client_id'],
            client_secret=self.config['client_secret'],
            scopes=self.SCOPES
        )
        
        # Always refresh the token
        creds.refresh(Request())
        self.save_tokens(creds)
        
        return creds

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

    def build_service(self):
        if not self.service:
            creds = self.authenticate()
            self.service = build('calendar', 'v3', credentials=creds)

    def update(self):
        current_time = datetime.datetime.now()
        if current_time - self.last_update < self.update_interval:
            return  # Skip update if not enough time has passed

        try:
            self.build_service()
            now = current_time.isoformat() + 'Z'  # 'Z' indicates UTC time
            events_result = self.service.events().list(calendarId='primary', timeMin=now,
                                                       maxResults=10, singleEvents=True,
                                                       orderBy='startTime').execute()
            self.events = events_result.get('items', [])
            self.last_update = current_time
        except Exception as e:
            logging.error(f"Error updating Calendar data: {e}")
            logging.error(traceback.format_exc())
            self.events = None  # Indicate that an error occurred

    def draw(self, screen, position):
        if self.font is None:
            # Initialize the font when drawing for the first time
            self.font = pygame.font.Font(None, 24)
        
        x, y = position
        if self.events is None:
            error_surface = self.font.render("Calendar Error", True, (255, 0, 0))
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
            event_surface = self.font.render(event_text, True, (200, 200, 200))
            screen.blit(event_surface, (x, y + y_offset))
            y_offset += 25

        if y_offset == 0:
            no_events_surface = self.font.render("No upcoming events", True, (200, 200, 200))
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