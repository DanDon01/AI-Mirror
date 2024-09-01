from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import datetime
import pygame

class CalendarModule:
    def __init__(self, config):
        self.SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        self.client_id = config['client_id']
        self.client_secret = config['client_secret']
        self.access_token = config['access_token']
        self.refresh_token = config['refresh_token']
        self.events = []
        self.font = None  # Initialize font to None
        self.last_update = datetime.datetime.min
        self.update_interval = datetime.timedelta(hours=24)  # Update daily
        self.service = None

    def authenticate(self):
        creds = Credentials(
            token=self.access_token,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.SCOPES
        )
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Update the stored access token
            self.access_token = creds.token
        return creds

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
            print(f"Error updating calendar data: {e}")
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