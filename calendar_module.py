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
        """Draw calendar with improved error handling"""
        try:
            # Extract x,y coordinates
            if isinstance(position, dict):
                x, y = position['x'], position['y']
            else:
                x, y = position
            
            # Initialize font if needed
            if self.font is None:
                try:
                    self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE)
                except Exception as e:
                    logging.error(f"Error loading font: {e}")
                    self.font = pygame.font.Font(None, FONT_SIZE)  # Fallback
            
            # Fix color values for background
            if not hasattr(self, 'bg_color') or not isinstance(self.bg_color, tuple) or len(self.bg_color) < 3:
                self.bg_color = (20, 20, 20)  # Default almost black
            else:
                # Ensure all color values are valid integers
                self.bg_color = tuple(max(0, min(255, int(c))) for c in self.bg_color[:3])
            
            # Fix header background color
            if not hasattr(self, 'header_bg_color') or not isinstance(self.header_bg_color, tuple) or len(self.header_bg_color) < 3:
                self.header_bg_color = (40, 40, 40)  # Default dark gray
            else:
                # Ensure all color values are valid integers
                self.header_bg_color = tuple(max(0, min(255, int(c))) for c in self.header_bg_color[:3])
            
            # Draw module background using the visual effects with fixed colors
            module_width = 300  # Fixed width
            module_height = 400  # Approximate height
            module_rect = pygame.Rect(x-10, y-10, module_width, module_height)
            
            try:
                self.effects.draw_rounded_rect(screen, module_rect, self.bg_color, radius=15)
                # Draw header
                header_rect = pygame.Rect(x-10, y-10, module_width, 40)
                self.effects.draw_rounded_rect(screen, header_rect, self.header_bg_color, radius=15)
            except ValueError as e:
                # Fallback if visual effects fail
                logging.error(f"Visual effects error: {e}")
                pygame.draw.rect(screen, self.bg_color, module_rect, border_radius=10)
                pygame.draw.rect(screen, self.header_bg_color, header_rect, border_radius=10)
            
            # Draw title
            title_font = pygame.font.Font(None, FONT_SIZE + 6)
            title_surface = title_font.render("Calendar", True, (220, 220, 220))
            screen.blit(title_surface, (x + 10, y + 5))
            
            # Draw calendar events
            current_y = y + 40  # Start below title
            
            # Debug message if no events
            if not self.events:
                debug_text = self.font.render("No calendar events", True, (180, 180, 180))
                screen.blit(debug_text, (x + 10, current_y))
                current_y += LINE_SPACING
                
                # Draw auth status
                auth_status = "Not authenticated" if not self.service else "Authenticated"
                status_color = (255, 100, 100) if not self.service else (100, 255, 100)
                status_text = self.font.render(auth_status, True, status_color)
                screen.blit(status_text, (x + 10, current_y))
                return
                
            # Draw events
            for event in self.events[:8]:  # Limit to 8 events
                # Draw event date/time
                start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', 'No date'))
                if isinstance(start, str):
                    if 'T' in start:
                        # This is a datetime
                        try:
                            dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                            date_str = dt.strftime('%a %H:%M')
                        except:
                            date_str = start[:10]
                    else:
                        # This is a date only
                        date_str = start
                else:
                    date_str = "Invalid date"
                    
                date_surface = self.font.render(date_str, True, (180, 180, 180))
                screen.blit(date_surface, (x + 10, current_y))
                
                # Draw event title
                title = event.get('summary', 'No title')
                if len(title) > 25:
                    title = title[:22] + "..."
                    
                title_surface = self.font.render(title, True, (230, 230, 230))
                screen.blit(title_surface, (x + 10, current_y + LINE_SPACING))
                
                current_y += LINE_SPACING * 2
                
                # Draw a separator line
                pygame.draw.line(screen, (50, 50, 50), 
                    (x + 5, current_y - 5), 
                    (x + module_width - 10, current_y - 5), 1)
        
        except Exception as e:
            logging.error(f"Error drawing calendar: {e}")
            logging.error(traceback.format_exc())
            
            # Draw error message
            try:
                error_font = pygame.font.Font(None, 24)
                error_text = error_font.render("Calendar Error", True, (255, 50, 50))
                screen.blit(error_text, (x + 10, y + 10))
            except:
                pass  # Last resort - if even error display fails

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
