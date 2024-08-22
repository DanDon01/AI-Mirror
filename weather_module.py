import requests
import pygame
import logging
from datetime import datetime, timedelta

class WeatherModule:
    def __init__(self, api_key, city):
        self.api_key = api_key
        self.city = city
        self.weather_data = None
        self.forecast_data = None
        self.font = pygame.font.Font(None, 24)
        self.last_update = datetime.min
        self.update_interval = timedelta(minutes=30)  # Update every 30 minutes

    def update(self):
        current_time = datetime.now()
        if current_time - self.last_update < self.update_interval:
            return  # Skip update if not enough time has passed

        try:
            # Current weather
            current_url = f"http://api.openweathermap.org/data/2.5/weather?q={self.city}&appid={self.api_key}&units=metric"
            current_response = requests.get(current_url)
            current_response.raise_for_status()
            self.weather_data = current_response.json()

            # 5-day forecast
            forecast_url = f"http://api.openweathermap.org/data/2.5/forecast?q={self.city}&appid={self.api_key}&units=metric"
            forecast_response = requests.get(forecast_url)
            forecast_response.raise_for_status()
            self.forecast_data = forecast_response.json()

            self.last_update = current_time
            logging.info("Weather data updated successfully")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch weather data: {e}")
            self.weather_data = None
            self.forecast_data = None

    def draw(self, screen, position):
        if self.weather_data and self.forecast_data:
            x, y = position
            
            # Current weather
            temp = self.weather_data['main']['temp']
            condition = self.weather_data['weather'][0]['main']
            humidity = self.weather_data['main']['humidity']
            wind_speed = self.weather_data['wind']['speed']
            
            current_text = f"{self.city}: {temp:.1f}°C, {condition}"
            details_text = f"Humidity: {humidity}%, Wind: {wind_speed} m/s"
            
            current_surface = self.font.render(current_text, True, (255, 255, 255))
            details_surface = self.font.render(details_text, True, (200, 200, 200))
            
            screen.blit(current_surface, (x, y))
            screen.blit(details_surface, (x, y + 30))
            
            # 3-day forecast
            for i in range(3):
                forecast = self.forecast_data['list'][i*8]  # Every 24 hours
                date = datetime.fromtimestamp(forecast['dt']).strftime('%A')
                temp = forecast['main']['temp']
                condition = forecast['weather'][0]['main']
                
                forecast_text = f"{date}: {temp:.1f}°C, {condition}"
                forecast_surface = self.font.render(forecast_text, True, (180, 180, 180))
                screen.blit(forecast_surface, (x, y + 60 + i*30))
            
            # Change LED color based on current weather condition
            led_color = self.get_led_color(condition)
            # Here you would implement the code to change the LEDs color.
            # Example: self.set_led_color(led_color)
        else:
            error_text = "Weather data unavailable"
            error_surface = self.font.render(error_text, True, (255, 0, 0))
            screen.blit(error_surface, position)

    def get_led_color(self, condition):
        condition = condition.lower()
        color_map = {
            'clear': (255, 255, 0),  # Yellow for clear weather
            'clouds': (200, 200, 200),  # Grey for cloudy weather
            'rain': (0, 0, 255),  # Blue for rainy weather
            'snow': (255, 255, 255),  # White for snow
            'thunderstorm': (255, 0, 0),  # Red for stormy weather
        }
        return color_map.get(condition, (255, 255, 255))  # Default white for unknown conditions

    def cleanup(self):
        pass  # No cleanup needed for this module
