import fitbit
from datetime import datetime, timedelta
import pygame
import logging

class FitbitModule:
    def __init__(self, config):
        self.client = fitbit.Fitbit(
            config['client_id'],
            config['client_secret'],
            access_token=config['access_token'],
            refresh_token=config['refresh_token'],
            system='en_US'
        )
        self.data = {
            'steps': 'N/A',
            'calories': 'N/A',
            'weight': 'N/A',
            'active_minutes': 'N/A',
            'sleep': 'N/A'
        }
        self.font = None
        self.last_update = datetime.min
        self.update_interval = timedelta(minutes=config.get('update_interval', 5))

    def update(self):
        current_time = datetime.now()
        if current_time - self.last_update < self.update_interval:
            return

        try:
            today = current_time.strftime("%Y-%m-%d")
            
            daily_data = self.client.activities(date=today)['summary']
            self.data['steps'] = daily_data['steps']
            self.data['calories'] = daily_data['caloriesOut']
            self.data['active_minutes'] = daily_data['fairlyActiveMinutes'] + daily_data['veryActiveMinutes']

            weight_data = self.client.body(date=today)['weight']
            self.data['weight'] = weight_data[0]['weight'] if weight_data else 'N/A'

            sleep_data = self.client.sleep(date=today)['summary']
            self.data['sleep'] = sleep_data['totalMinutesAsleep']

            self.last_update = current_time
            logging.info("Fitbit data updated successfully")
        except Exception as e:
            logging.error(f"Error fetching Fitbit data: {e}")

    def draw(self, screen, position):
        if self.font is None:
            self.font = pygame.font.Font(None, 36)

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
        pass