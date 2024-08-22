import fitbit
from datetime import datetime, timedelta
import pygame
import logging

class FitbitModule:
    def __init__(self, client_id, client_secret, access_token, refresh_token):
        self.client = fitbit.Fitbit(
            client_id, client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            system='en_US'
        )
        self.data = {
            'steps': 'N/A',
            'calories': 'N/A',
            'weight': 'N/A',
            'active_minutes': 'N/A',
            'sleep': 'N/A'
        }
        self.font = pygame.font.Font(None, 36)
        self.last_update = datetime.min
        self.update_interval = timedelta(minutes=5)  # Update every 5 minutes

    def update(self):
        current_time = datetime.now()
        if current_time - self.last_update < self.update_interval:
            return  # Skip update if not enough time has passed

        try:
            today = current_time.strftime("%Y-%m-%d")
            
            # Fetch all daily activity data in one API call
            daily_data = self.client.activities(date=today)['summary']
            self.data['steps'] = daily_data['steps']
            self.data['calories'] = daily_data['caloriesOut']
            self.data['active_minutes'] = daily_data['fairlyActiveMinutes'] + daily_data['veryActiveMinutes']

            # Fetch weight data
            weight_data = self.client.body(date=today)['weight']
            self.data['weight'] = weight_data[0]['weight'] if weight_data else 'N/A'

            # Fetch sleep data
            sleep_data = self.client.sleep(date=today)['summary']
            self.data['sleep'] = sleep_data['totalMinutesAsleep']

            self.last_update = current_time
            logging.info("Fitbit data updated successfully")
        except Exception as e:
            logging.error(f"Error fetching Fitbit data: {e}")

    def draw(self, screen, position):
        try:
            x, y = position
            labels = [
                f"Steps: {self.data['steps']}",
                f"Calories: {self.data['calories']}",
                f"Weight: {self.data['weight']} kg",
                f"Active Minutes: {self.data['active_minutes']}",
                f"Sleep: {self.data['sleep']} mins"
            ]
            for i, label in enumerate(labels):
                text_surface = self.font.render(label, True, (255, 255, 255))
                screen.blit(text_surface, (x, y + i * 40))
        except Exception as e:
            logging.error(f"Error drawing Fitbit data: {e}")
            error_surface = self.font.render("Fitbit data unavailable", True, (255, 0, 0))
            screen.blit(error_surface, position)

    def cleanup(self):
        # No specific cleanup needed for Fitbit module
        pass

