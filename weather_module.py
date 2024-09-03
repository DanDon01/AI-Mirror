import requests
import pygame
import logging
from datetime import datetime, timedelta
from config import FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_PASTEL_RED, LINE_SPACING, TRANSPARENCY
import os
from weather_animations import CloudAnimation, RainAnimation, SunAnimation, StormAnimation, SnowAnimation, MoonAnimation

class WeatherModule:
    def __init__(self, api_key, city_id):
        self.api_key = api_key
        self.city = city_id
        self.weather_data = None
        self.font = None
        self.last_update = datetime.min
        self.update_interval = timedelta(minutes=30)
        self.screen_width = 800  # Set a default value
        self.screen_height = 600  # Set a default value
        self.animation = None

    def update(self):
        current_time = datetime.now()
        if current_time - self.last_update < self.update_interval:
            return

        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={self.city}&appid={self.api_key}&units=metric"
            response = requests.get(url)
            response.raise_for_status()
            self.weather_data = response.json()

            # Set animation based on weather condition
            self.update_animation()

            self.last_update = current_time
            logging.info("Weather data updated successfully")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch weather data: {e}")
            self.weather_data = None
            self.animation = None
        except Exception as e:
            logging.error(f"Error updating weather: {e}")
            self.animation = None

    def update_animation(self):
        try:
            weather_main = self.weather_data['weather'][0]['main'].lower()
            weather_description = self.weather_data['weather'][0]['description'].lower()

            if 'clear' in weather_main:
                self.animation = SunAnimation(self.screen_width, self.screen_height)
            elif 'cloud' in weather_main or 'broken' in weather_description:
                partly = 'partly' in weather_description or 'broken' in weather_description
                self.animation = CloudAnimation(self.screen_width, self.screen_height, partly=partly)
            elif 'rain' in weather_main:
                heavy = 'heavy' in weather_description
                self.animation = RainAnimation(self.screen_width, self.screen_height, heavy=heavy)
            elif 'thunderstorm' in weather_main:
                self.animation = StormAnimation(self.screen_width, self.screen_height)
            elif 'snow' in weather_main:
                self.animation = SnowAnimation(self.screen_width, self.screen_height)
            else:
                self.animation = None
        except Exception as e:
            logging.error(f"Error creating weather animation: {e}")
            self.animation = None

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

            # Update and draw weather animation
            if self.animation:
                self.animation.update()
                self.animation.draw(screen)

        else:
            error_text = "Weather data unavailable"
            error_surface = self.font.render(error_text, True, COLOR_PASTEL_RED)
            error_surface.set_alpha(TRANSPARENCY)
            screen.blit(error_surface, position)

    def cleanup(self):
        pass
