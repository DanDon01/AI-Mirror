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
from config import FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_PASTEL_RED, LINE_SPACING, TRANSPARENCY, CONFIG, COLOR_BG_MODULE_ALPHA, COLOR_BG_HEADER_ALPHA
from visual_effects import VisualEffects
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
        
        # Add visual enhancement properties
        self.effects = VisualEffects()
        self.last_update_time = time.time()
        self.event_fade_in = {}  # Store fade-in progress for each event
        self.header_pulse_speed = 0.3
        
        # Background colors
        self.bg_color = COLOR_BG_MODULE_ALPHA
        self.header_bg_color = COLOR_BG_HEADER_ALPHA
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
        """Draw calendar with proper Google Calendar colors and consistent styling"""
        try:
            # Extract x,y coordinates
            if isinstance(position, dict):
                x, y = position['x'], position['y']
            else:
                x, y = position
            
            # Get styling from config
            styling = CONFIG.get('module_styling', {})
            fonts = styling.get('fonts', {})
            backgrounds = styling.get('backgrounds', {})
            
            # Initialize fonts if not already done
            if not self.font:
                title_size = fonts.get('title', {}).get('size', 24)
                body_size = fonts.get('body', {}).get('size', 16)
                small_size = fonts.get('small', {}).get('size', 14)
                
                self.title_font = pygame.font.SysFont(FONT_NAME, title_size)
                self.font = pygame.font.SysFont(FONT_NAME, body_size)
                self.small_font = pygame.font.SysFont(FONT_NAME, small_size)
            
            # Get background colors - Use transparent backgrounds 
            bg_color = COLOR_BG_MODULE_ALPHA
            header_bg_color = COLOR_BG_HEADER_ALPHA
            
            # Draw module background
            module_width = 225  # Fixed width, reduced from 300 by 25%
            module_height = 400  # Approximate height
            module_rect = pygame.Rect(x-10, y-10, module_width, module_height)
            
            # Get styles for drawing
            radius = styling.get('radius', 15)
            padding = styling.get('spacing', {}).get('padding', 10)
            line_height = styling.get('spacing', {}).get('line_height', 22)
            
            try:
                # Draw background with rounded corners and transparency
                self.effects.draw_rounded_rect(screen, module_rect, bg_color, radius=radius, alpha=0)
                # Draw header
                header_rect = pygame.Rect(x-10, y-10, module_width, 40)
                self.effects.draw_rounded_rect(screen, header_rect, header_bg_color, radius=radius, alpha=0)
            except Exception as e:
                # Fallback if visual effects fail
                from config import draw_module_background_fallback
                draw_module_background_fallback(screen, x, y, module_width, module_height, padding=10)
            
            # Draw title
            title_color = fonts.get('title', {}).get('color', (240, 240, 240))
            title_surface = self.title_font.render("Calendar", True, title_color)
            screen.blit(title_surface, (x + padding, y + padding))
            
            # Draw calendar events
            current_y = y + 45  # Start below title
            
            # Debug message if no events
            if not self.events:
                debug_color = fonts.get('body', {}).get('color', (200, 200, 200))
                debug_text = self.font.render("No calendar events", True, debug_color)
                screen.blit(debug_text, (x + padding, current_y))
                return
            
            # Draw events with proper Google Colors but consistent font styling
            for event in self.events[:8]:  # Limit to 8 events
                try:
                    # Get event color from colorId if available
                    event_color = self.get_event_color(event)
                    
                    # Draw colored indicator bar
                    indicator_rect = pygame.Rect(x + 5, current_y + 2, 5, 25)
                    pygame.draw.rect(screen, event_color, indicator_rect, border_radius=2)
                    
                    # Format start time/date
                    start = event.get('start', {})
                    if 'dateTime' in start:
                        try:
                            dt = datetime.datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                            date_str = dt.strftime('%a %H:%M')
                        except:
                            date_str = start['dateTime'][:16].replace('T', ' ')
                    else:
                        # All-day event
                        date_str = "All day"
                    
                    # Draw event time with adjusted position (after indicator)
                    small_color = fonts.get('small', {}).get('color', (180, 180, 180))
                    date_surface = self.small_font.render(date_str, True, small_color)
                    screen.blit(date_surface, (x + 15, current_y))
                    
                    # Draw event title with color influence
                    title = event.get('summary', 'No title')
                    if len(title) > 28:
                        title = title[:25] + "..."
                    
                    # Use event color for title, but maintain consistent brightness level
                    title_surface = self.font.render(title, True, event_color)
                    screen.blit(title_surface, (x + 15, current_y + 18))
                    
                    current_y += 40
                    
                    # Draw a separator line
                    pygame.draw.line(screen, (50, 50, 50), 
                        (x + 5, current_y - 5), 
                        (x + module_width - 25, current_y - 5), 1)
                except Exception as e:
                    # If specific event drawing fails, log and continue to next event
                    logging.error(f"Error drawing event: {e}")
                    current_y += 30
        
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
                except:
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
