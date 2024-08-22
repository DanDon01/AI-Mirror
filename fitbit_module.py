import fitbit
from datetime import datetime
import pygame

class FitbitModule:
    def __init__(self, client_id, client_secret, access_token, refresh_token):
        self.client = fitbit.Fitbit(client_id, client_secret,
                                    access_token=access_token,
                                    refresh_token=refresh_token)
        self.data = {
            'steps': 'N/A',
            'calories': 'N/A',
            'weight': 'N/A',
            'hourly_activity': 'N/A',
            'sleep': 'N/A'
        }
        self.font = pygame.font.Font(None, 36)  # Default font for drawing

    def update(self):
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Fetching steps data
            steps_data = self.client.activities(date=today)['summary']['steps']
            self.data['steps'] = steps_data
            
            # Fetching calories data
            calories_data = self.client.activities(date=today)['summary']['caloriesOut']
            self.data['calories'] = calories_data
            
            # Fetching weight data
            weight_data = self.client.body(date=today)['weight']
            self.data['weight'] = weight_data
            
            # Fetching hourly activity
            hourly_data = self.client.activities(date=today)['summary']['fairlyActiveMinutes']
            self.data['hourly_activity'] = hourly_data

            # Fetching sleep data
            sleep_data = self.client.sleep(date=today)['summary']['totalMinutesAsleep']
            self.data['sleep'] = sleep_data

        except Exception as e:
            print(f"Error fetching Fitbit data: {e}")

    def draw(self, screen, position):
        try:
            x, y = position

            # Drawing the Fitbit data
            steps_surface = self.font.render(f"Steps: {self.data['steps']}", True, (255, 255, 255))
            screen.blit(steps_surface, (x, y))

            calories_surface = self.font.render(f"Calories: {self.data['calories']}", True, (255, 255, 255))
            screen.blit(calories_surface, (x, y + 40))

            weight_surface = self.font.render(f"Weight: {self.data['weight']} kg", True, (255, 255, 255))
            screen.blit(weight_surface, (x, y + 80))

            hourly_activity_surface = self.font.render(f"Active Minutes: {self.data['hourly_activity']}", True, (255, 255, 255))
            screen.blit(hourly_activity_surface, (x, y + 120))

            sleep_surface = self.font.render(f"Sleep: {self.data['sleep']} mins", True, (255, 255, 255))
            screen.blit(sleep_surface, (x, y + 160))

        except Exception as e:
            print(f"Error drawing Fitbit data: {e}")

