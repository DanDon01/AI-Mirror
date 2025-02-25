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
from google_auth_oauthlib.flow import Flow
from config import FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_PASTEL_RED, LINE_SPACING, TRANSPARENCY
from visual_effects import VisualEffects
import time

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
        
        # Add visual enhancement properties
        self.effects = VisualEffects()
        self.last_update_time = time.time()
        self.event_fade_in = {}  # Store fade-in progress for each event
        self.header_pulse_speed = 0.3
        
        # Background colors
        self.bg_color = (20, 20, 20, 180)
        self.header_bg_color = (40, 40, 40, 200)
        self.today_bg_color = (0, 40, 80, 180)  # Bluish for today's events

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
            self.events = events_result.get('items', [])
            logging.info(f"Successfully updated calendar events. Number of events fetched: {len(self.events)}")
            self.last_update = current_time
        except Exception as e:
            logging.error(f"Error updating Calendar data: {e}")
            logging.error(traceback.format_exc())
            self.events = None

    def draw(self, screen, position):
        x, y = position
        original_y = y
        
        # Calculate module dimensions
        module_width = 300  # Adjust based on your layout
        module_height = min(400, (len(self.events) + 2) * 30)  # Limit height
        
        # Draw module background
        module_rect = pygame.Rect(x-10, y-10, module_width, module_height)
        self.effects.draw_rounded_rect(screen, module_rect, self.bg_color, radius=15)
        
        # Draw header with pulsing effect
        header_rect = pygame.Rect(x-10, y-10, module_width, 40)
        header_alpha = self.effects.pulse_effect(180, 220, self.header_pulse_speed)
        self.effects.draw_rounded_rect(screen, header_rect, self.header_bg_color, radius=15, alpha=header_alpha)
        
        # Draw title with shadow
        title_text = self.effects.create_text_with_shadow(
            self.font, "Calendar", (220, 220, 220), offset=2)
        screen.blit(title_text, (x + 5, y))
        
        y += 40  # Move down past header
        
        # Group events by date
        events_by_date = {}
        for event in self.events:
            date_str = event['start'].get('dateTime', event['start'].get('date')).split('T')[0]
            if date_str not in events_by_date:
                events_by_date[date_str] = []
            events_by_date[date_str].append(event)
        
        # Get today's date
        today = datetime.date.today().strftime('%Y-%m-%d')
        
        # Initialize event fade-in for new events
        current_events = set(e['id'] for e in self.events)
        for event_id in list(self.event_fade_in.keys()):
            if event_id not in current_events:
                del self.event_fade_in[event_id]
        
        for event in self.events:
            if event['id'] not in self.event_fade_in:
                self.event_fade_in[event['id']] = 0.0
        
        # Update fade-in progress
        elapsed = time.time() - self.last_update_time
        fade_speed = 2.0  # Adjust for faster/slower fade
        
        for event_id in self.event_fade_in:
            self.event_fade_in[event_id] = min(1.0, self.event_fade_in[event_id] + elapsed * fade_speed)
        
        self.last_update_time = time.time()
        
        # Draw events by date
        for date_str, date_events in sorted(events_by_date.items()):
            # Check if this is today
            is_today = (date_str == today)
            
            # Format date header
            date_obj = datetime.date.fromisoformat(date_str)
            if is_today:
                date_header = "Today"
            elif date_obj.strftime('%Y-%m-%d') == (datetime.date.today() + datetime.timedelta(days=1)).strftime('%Y-%m-%d'):
                date_header = "Tomorrow"
            else:
                date_header = date_obj.strftime('%A, %b %d')
            
            # Draw date header with appropriate styling
            date_color = (180, 220, 255) if is_today else (180, 180, 180)
            date_text = self.effects.create_text_with_shadow(
                self.font, date_header, date_color, offset=1)
            
            # Draw date background if it's today
            if is_today:
                date_rect = pygame.Rect(x-5, y-2, module_width-10, 25)
                self.effects.draw_rounded_rect(screen, date_rect, self.today_bg_color, radius=8)
            
            screen.blit(date_text, (x + 5, y))
            y += 25
            
            # Draw events for this date with fade-in effect
            for event in date_events:
                # Calculate alpha based on fade-in progress
                alpha = int(255 * self.event_fade_in[event['id']])
                
                # Format time
                start = event['start'].get('dateTime', event['start'].get('date'))
                if 'T' in start:  # This is a datetime
                    start_date = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                    time_str = start_date.strftime("%H:%M")
                else:  # This is a date
                    start_date = datetime.date.fromisoformat(start)
                    time_str = "All day"
                
                if isinstance(start_date, datetime.datetime):
                    start_date = start_date.date()
                
                if start_date < datetime.date.today():
                    continue  # Skip past events
                
                if start_date > datetime.date.today() + datetime.timedelta(days=7):
                    break  # Don't show events more than a week in the future
                
                # Determine color based on event type or calendar
                event_color = (220, 220, 220)  # Default color
                
                # Create text surfaces with shadow
                time_surface = self.font.render(time_str, True, (160, 160, 160))
                title_surface = self.font.render(event['summary'], True, event_color)
                
                # Apply fade-in
                time_surface.set_alpha(alpha)
                title_surface.set_alpha(alpha)
                
                # Draw with better alignment
                screen.blit(time_surface, (x + 5, y))
                screen.blit(title_surface, (x + 60, y))  # Adjust position as needed
                
                y += 22  # Slightly smaller spacing between events
            
            y += 10  # Add space between date groups
        
        # If no events, show a message
        if not self.events:
            no_events = self.effects.create_text_with_shadow(
                self.font, "No upcoming events", (150, 150, 150), offset=1)
            screen.blit(no_events, (x + 20, y + 20))

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
