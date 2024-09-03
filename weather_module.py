import requests
import pygame
import logging
from datetime import datetime, timedelta
from config import FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_PASTEL_RED, LINE_SPACING, TRANSPARENCY
import os

class WeatherModule:
    def __init__(self, api_key, city):
        self.api_key = api_key
        self.city = city
        self.weather_data = None
        self.font = None
        self.last_update = datetime.min
        self.update_interval = timedelta(minutes=30)
        self.icon = None

    def update(self):
        current_time = datetime.now()
        if current_time - self.last_update < self.update_interval:
            return

        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={self.city}&appid={self.api_key}&units=metric"
            response = requests.get(url)
            response.raise_for_status()
            self.weather_data = response.json()

            # Fetch weather icon
            icon_id = self.weather_data['weather'][0]['icon']
            icon_url = f"http://openweathermap.org/img/wn/{icon_id}@2x.png"
            icon_response = requests.get(icon_url)
            icon_response.raise_for_status()
            icon_path = os.path.join(os.path.dirname(__file__), f"{icon_id}.png")
            with open(icon_path, 'wb') as icon_file:
                icon_file.write(icon_response.content)
            self.icon = pygame.image.load(icon_path)

            self.last_update = current_time
            logging.info("Weather data updated successfully")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch weather data: {e}")
            self.weather_data = None
            self.icon = None

    def draw(self, screen, position):
        if self.font is None:
            try:
                self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE)
            except:
                print(f"Warning: Font '{FONT_NAME}' not found. Using default font.")
                self.font = pygame.font.Font(None, FONT_SIZE)

        if self.weather_data:
            x, y = position
            
            # Current weather
            temp = self.weather_data['main']['temp']
            condition = self.weather_data['weather'][0]['description'].capitalize()
            humidity = self.weather_data['main']['humidity']
            wind_speed = self.weather_data['wind']['speed']
            feels_like = self.weather_data['main']['feels_like']
            pressure = self.weather_data['main']['pressure']
            
            # Calculate chance of rain (this is an approximation)
            rain_chance = self.weather_data['clouds']['all']  # Cloud coverage as a proxy for rain chance

            lines = [
                f"{self.city}: {temp:.1f}°C, {condition}",
                f"Feels like: {feels_like:.1f}°C",
                f"Humidity: {humidity}%",
                f"Wind: {wind_speed} m/s",
                f"Pressure: {pressure} hPa",
                f"Chance of rain: {rain_chance}%"
            ]

            for i, line in enumerate(lines):
                text_surface = self.font.render(line, True, COLOR_FONT_DEFAULT)
                text_surface.set_alpha(TRANSPARENCY)
                screen.blit(text_surface, (x, y + i * LINE_SPACING))

            # Display weather icon
            if self.icon:
                screen.blit(self.icon, (x + 200, y))

        else:
            error_text = "Weather data unavailable"
            error_surface = self.font.render(error_text, True, COLOR_PASTEL_RED)
            error_surface.set_alpha(TRANSPARENCY)
            screen.blit(error_surface, position)

    def cleanup(self):
        # Remove downloaded icon file
        if self.icon:
            icon_path = os.path.join(os.path.dirname(__file__), f"{self.weather_data['weather'][0]['icon']}.png")
            if os.path.exists(icon_path):
                os.remove(icon_path)
