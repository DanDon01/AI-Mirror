from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
import os
import datetime
import pygame
import logging

class CalendarModule:
    def __init__(self, credentials_file, token_file):
        self.SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.events = []
        self.font = pygame.font.Font(None, 24)
        self.last_update = datetime.datetime.min
        self.update_interval = datetime.timedelta(minutes=15)

    def authenticate(self):
        creds = None
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
        return creds

    def update(self):
        current_time = datetime.datetime.now()
        if current_time - self.last_update < self.update_interval:
            return  # Skip update if not enough time has passed

        try:
            creds = self.authenticate()
            service = build('calendar', 'v3', credentials=creds)

            now = datetime.datetime.utcnow().isoformat() + 'Z'
            events_result = service.events().list(calendarId='primary', timeMin=now,
                                                  maxResults=5, singleEvents=True,
                                                  orderBy='startTime').execute()
            self.events = events_result.get('items', [])
            self.last_update = current_time
            logging.info("Calendar data updated successfully")
        except Exception as e:
            logging.error(f"Error updating calendar data: {e}")

    def draw(self, screen, position):
        try:
            x, y = position
            title_surface = self.font.render("Upcoming Events:", True, (255, 255, 255))
            screen.blit(title_surface, (x, y))
            y += 30

            if not self.events:
                no_events_surface = self.font.render("No upcoming events", True, (200, 200, 200))
                screen.blit(no_events_surface, (x, y))
            else:
                for event in self.events:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    start_dt = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                    event_text = f"{start_dt.strftime('%m/%d %H:%M')} - {event['summary']}"
                    event_surface = self.font.render(event_text, True, (200, 200, 200))
                    screen.blit(event_surface, (x, y))
                    y += 25
        except Exception as e:
            logging.error(f"Error drawing calendar data: {e}")
            error_surface = self.font.render("Calendar data unavailable", True, (255, 0, 0))
            screen.blit(error_surface, position)

    def cleanup(self):
        pass  # No specific cleanup needed for this module
