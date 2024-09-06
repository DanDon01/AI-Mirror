import requests
import pygame
import logging
from datetime import datetime, timedelta
from config import FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_PASTEL_RED, LINE_SPACING, TRANSPARENCY
import os
from weather_animations import CloudAnimation, RainAnimation, SunAnimation, StormAnimation, SnowAnimation, MoonAnimation

class WeatherModule:
    def __init__(self, api_key, city, screen_width=800, screen_height=600, icons_path=None):
        self.api_key = api_key
        self.city = city
        self.weather_data = None
        self.font = None
        self.last_update = datetime.min
        self.update_interval = timedelta(minutes=30)
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.animation = None
        self.icons_path = icons_path  # Add this line

    def update(self):
        current_time = datetime.now()
        if current_time - self.last_update < self.update_interval:
            logging.debug("Skipping weather update: Not enough time has passed since last update")  # Changed to debug
            return

        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={self.city}&appid={self.api_key}&units=metric"
            response = requests.get(url)
            response.raise_for_status()
            self.weather_data = response.json()

            # Print the city name and country returned by the API for debugging
            print(f"Weather data received for: {self.weather_data['name']}, {self.weather_data['sys']['country']}")

            # Set animation based on weather condition
            self.update_animation()

            self.last_update = current_time
            logging.info(f"Weather data updated successfully for {self.city}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch weather data for {self.city}: {e}")
            self.weather_data = None
            self.animation = None
        except Exception as e:
            logging.error(f"Error updating weather for {self.city}: {e}")
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

    def get_temperature_color(self, temperature):
        # Clamp temperature between 0 and 32
        t = max(0, min(temperature, 32))
        
        if t <= 15:
            # White (255, 255, 255) to Blue (0, 0, 255)
            ratio = t / 15
            r = int(255 * (1 - ratio))
            g = int(255 * (1 - ratio))
            b = 255
        elif t <= 21:
            # Blue (0, 0, 255) to Yellow (255, 255, 0)
            ratio = (t - 15) / 6
            r = int(255 * ratio)
            g = int(255 * ratio)
            b = int(255 * (1 - ratio))
        else:
            # Yellow (255, 255, 0) to Red (255, 0, 0)
            ratio = (t - 21) / 11
            r = 255
            g = int(255 * (1 - ratio))
            b = 0
        
        return (r, g, b)

    def draw(self, screen, position):
        if self.font is None:
            try:
                self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE)
            except:
                print(f"Warning: Font '{FONT_NAME}' not found. Using default font.")
                self.font = pygame.font.Font(None, FONT_SIZE)

        if self.weather_data:
            x, y = position
            
            # Get city name and country code from the weather data
            city_name = self.weather_data['name']
            country_code = self.weather_data['sys']['country']
            
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
                f"{city_name}, {country_code}: {temp:.1f}°C, {condition}",
                f"Feels like: {feels_like:.1f}°C",
                f"Humidity: {humidity}%",
                f"Wind: {wind_speed} m/s",
                f"Pressure: {pressure} hPa",
                f"Chance of rain: {rain_chance}%"
            ]

            for i, line in enumerate(lines):
                if "Feels like" in line:
                    color = self.get_temperature_color(feels_like)
                else:
                    color = COLOR_FONT_DEFAULT
                text_surface = self.font.render(line, True, color)
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
