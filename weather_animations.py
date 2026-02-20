import pygame
import random
import os
import logging

logger = logging.getLogger("WeatherAnimations")

class WeatherAnimation:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.particles = []
        # Update the icon_path to use an absolute path
        self.icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'weather_icons')

    def update(self):
        pass

    def draw(self, screen):
        pass

    def load_image(self, filename):
        try:
            full_path = os.path.join(self.icon_path, filename)
            return pygame.image.load(full_path).convert_alpha()
        except pygame.error as e:
            logger.warning(f"Error loading image {filename}: {e}")
            # Return a dummy surface if the image can't be loaded
            return pygame.Surface((50, 50))

class CloudAnimation(WeatherAnimation):
    def __init__(self, screen_width, screen_height, partly=False):
        super().__init__(screen_width, screen_height)
        self.image = self.load_image('partly_cloudy.png' if partly else 'cloudy.png')
        self.clouds = [
            {'x': random.randint(0, screen_width), 'y': random.randint(0, 100), 'speed': random.uniform(0.5, 1.5)}
            for _ in range(5)
        ]

    def update(self):
        for cloud in self.clouds:
            cloud['x'] += cloud['speed']
            if cloud['x'] > self.screen_width:
                cloud['x'] = -self.image.get_width()
                cloud['y'] = random.randint(0, 100)

    def draw(self, screen):
        for cloud in self.clouds:
            screen.blit(self.image, (cloud['x'], cloud['y']))

class RainAnimation(WeatherAnimation):
    def __init__(self, screen_width, screen_height, heavy=False):
        super().__init__(screen_width, screen_height)
        self.image = self.load_image('heavy_rain.png' if heavy else 'rainy.png')
        self.drops = [
            {'x': random.randint(0, screen_width), 'y': random.randint(0, screen_height), 'speed': random.uniform(5, 15)}
            for _ in range(50)
        ]

    def update(self):
        for drop in self.drops:
            drop['y'] += drop['speed']
            if drop['y'] > self.screen_height:
                drop['y'] = 0
                drop['x'] = random.randint(0, self.screen_width)

    def draw(self, screen):
        screen.blit(self.image, (0, 0))
        for drop in self.drops:
            pygame.draw.line(screen, (100, 100, 255), (drop['x'], drop['y']), (drop['x'], drop['y'] + 5), 2)

class SunAnimation(WeatherAnimation):
    def __init__(self, screen_width, screen_height):
        super().__init__(screen_width, screen_height)
        self.image = self.load_image('sunny.png')
        self.x = -self.image.get_width()

    def update(self):
        self.x += 1
        if self.x > self.screen_width:
            self.x = -self.image.get_width()

    def draw(self, screen):
        screen.blit(self.image, (self.x, 50))

class StormAnimation(WeatherAnimation):
    def __init__(self, screen_width, screen_height):
        super().__init__(screen_width, screen_height)
        self.cloud_image = self.load_image('thunderstorm.png')
        self.lightning_image = self.load_image('lightning.png')
        self.lightning_timer = 0
        self.show_lightning = False
        self.lightning_pos = (0, 0)

    def update(self):
        self.lightning_timer += 1
        if self.lightning_timer > 60:
            self.show_lightning = random.choice([True, False])
            self.lightning_timer = 0
            if self.show_lightning:
                self.lightning_pos = (random.randint(0, self.screen_width - self.lightning_image.get_width()),
                                      random.randint(0, self.screen_height - self.lightning_image.get_height()))

    def draw(self, screen):
        screen.blit(self.cloud_image, (0, 0))
        if self.show_lightning:
            screen.blit(self.lightning_image, self.lightning_pos)

class SnowAnimation(WeatherAnimation):
    def __init__(self, screen_width, screen_height):
        super().__init__(screen_width, screen_height)
        self.image = self.load_image('snowy.png')
        self.flakes = [
            {'x': random.randint(0, screen_width), 'y': random.randint(0, screen_height), 'speed': random.uniform(1, 3), 'size': random.randint(2, 5)}
            for _ in range(100)
        ]

    def update(self):
        for flake in self.flakes:
            flake['y'] += flake['speed']
            flake['x'] += random.uniform(-1, 1)
            if flake['y'] > self.screen_height:
                flake['y'] = 0
                flake['x'] = random.randint(0, self.screen_width)

    def draw(self, screen):
        screen.blit(self.image, (0, 0))
        for flake in self.flakes:
            pygame.draw.circle(screen, (255, 255, 255), (int(flake['x']), int(flake['y'])), flake['size'])

class MoonAnimation(WeatherAnimation):
    def __init__(self, screen_width, screen_height, cloudy=False):
        super().__init__(screen_width, screen_height)
        self.image = self.load_image('moon_cloudy.png' if cloudy else 'moon.png')
        self.x = -self.image.get_width()

    def update(self):
        self.x += 0.5
        if self.x > self.screen_width:
            self.x = -self.image.get_width()

    def draw(self, screen):
        screen.blit(self.image, (self.x, 50))