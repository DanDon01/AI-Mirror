import requests
import pygame
import logging
from datetime import datetime, timedelta

class SmartHomeModule:
    def __init__(self, ha_url, access_token, entities, font_size=24, color=(255, 255, 255), 
                 update_interval_minutes=1, retry_attempts=3, timeout=10):
        self.ha_url = ha_url
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "content-type": "application/json",
        }
        self.entities = entities
        self.data = {}
        self.font = pygame.font.Font(None, font_size)
        self.color = color
        self.last_update = datetime.min
        self.update_interval = timedelta(minutes=update_interval_minutes)
        self.retry_attempts = retry_attempts
        self.timeout = timeout
        self.error_color = (255, 0, 0)  # Red color for error messages

    def update(self):
        current_time = datetime.now()
        if current_time - self.last_update < self.update_interval:
            return

        for entity_id in self.entities:
            success = False
            for attempt in range(self.retry_attempts):
                try:
                    response = requests.get(f"{self.ha_url}/api/states/{entity_id}", 
                                            headers=self.headers, timeout=self.timeout)
                    response.raise_for_status()
                    state = response.json()
                    self.data[entity_id] = {
                        'state': state['state'],
                        'attributes': state['attributes'],
                        'last_updated': current_time,
                        'status': 'ok'
                    }
                    success = True
                    break
                except requests.RequestException as e:
                    logging.warning(f"Attempt {attempt+1}/{self.retry_attempts}: Error fetching data for {entity_id}: {e}")
                    if attempt < self.retry_attempts - 1:
                        continue
                    self.data[entity_id] = {
                        'state': 'Error',
                        'attributes': {},
                        'last_updated': current_time,
                        'status': 'error'
                    }
            if not success:
                logging.error(f"Failed to update {entity_id} after {self.retry_attempts} attempts.")

        self.last_update = current_time

    def draw(self, screen, position):
        x, y = position
        for entity_id, data in self.data.items():
            friendly_name = data['attributes'].get('friendly_name', entity_id)
            state = data['state']
            unit = data['attributes'].get('unit_of_measurement', '')
            status = data['status']

            # Format the text
            text = f"{friendly_name}: {state} {unit}".strip()
            
            # Choose color based on status
            color = self.error_color if status == 'error' else self.color

            # Render text
            text_surface = self.font.render(text, True, color)
            screen.blit(text_surface, (x, y))

            # Add last updated time
            if 'last_updated' in data:
                last_updated = data['last_updated'].strftime("%H:%M:%S")
                updated_text = f"Updated: {last_updated}"
                updated_surface = pygame.font.Font(None, int(self.font.get_height() * 0.75)).render(updated_text, True, (150, 150, 150))
                screen.blit(updated_surface, (x + self.font.size(text)[0] + 10, y + 5))

            y += self.font.get_height() + 5  # Move down for the next item

    def cleanup(self):
        pass  # No cleanup needed for this module
