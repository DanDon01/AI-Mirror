import requests

class WeatherModule:
    def __init__(self, api_key, city):
        self.api_key = api_key
        self.city = city
        self.weather_data = None

    def update(self):
        url = f"http://api.openweathermap.org/data/2.5/weather?q={self.city}&appid={self.api_key}&units=metric"
        response = requests.get(url)
        if response.status_code == 200:
            self.weather_data = response.json()
        else:
            raise Exception(f"Failed to fetch weather data: {response.status_code}")

    def draw(self, screen, position):
        if self.weather_data:
            temp = self.weather_data['main']['temp']
            condition = self.weather_data['weather'][0]['main']
            text = f"{self.city}: {temp}°C, {condition}"
            font = pygame.font.Font(None, 24)
            text_surface = font.render(text, True, (255, 255, 255))
            screen.blit(text_surface, position)

    def cleanup(self):
        # No cleanup needed for this module
        pass
