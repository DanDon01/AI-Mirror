import requests
import pygame

class WeatherModule:
    def __init__(self, api_key, city):
        self.api_key = api_key
        self.city = city
        self.weather_data = None
        self.font = pygame.font.Font(None, 24)  # Default font for drawing

    def update(self):
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={self.city}&appid={self.api_key}&units=metric"
            response = requests.get(url)
            response.raise_for_status()  # Raises an HTTPError if the status is 4xx, 5xx
            self.weather_data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch weather data: {e}")
            self.weather_data = None

    def draw(self, screen, position):
        if self.weather_data:
            temp = self.weather_data['main']['temp']
            condition = self.weather_data['weather'][0]['main']
            text = f"{self.city}: {temp}°C, {condition}"
            text_surface = self.font.render(text, True, (255, 255, 255))
            screen.blit(text_surface, position)

            # Change LED color based on weather condition
            led_color = self.get_led_color(condition)
            # Here you would implement the code to change the LEDs color.
            # This could be a call to another module that interfaces with your LED hardware.
            # Example: self.set_led_color(led_color)

    def get_led_color(self, condition):
        """
        Determine LED color based on weather condition.
        """
        condition = condition.lower()
        if 'clear' in condition:
            return (255, 255, 0)  # Yellow for clear weather
        elif 'clouds' in condition:
            return (200, 200, 200)  # Grey for cloudy weather
        elif 'rain' in condition:
            return (0, 0, 255)  # Blue for rainy weather
        elif 'snow' in condition:
            return (255, 255, 255)  # White for snow
        elif 'storm' in condition:
            return (255, 0, 0)  # Red for stormy weather
        else:
            return (255, 255, 255)  # Default white for unknown conditions

    def cleanup(self):
        # No cleanup needed for this module, but it's here if needed for future expansions.
        pass
