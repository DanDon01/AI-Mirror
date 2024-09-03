import pygame
import random

class WeatherAnimation:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.particles = []

    def update(self):
        pass

    def draw(self, screen):
        pass

class CloudAnimation(WeatherAnimation):
    def __init__(self, screen_width, screen_height):
        super().__init__(screen_width, screen_height)
        self.clouds = [
            {'x': random.randint(0, screen_width), 'y': random.randint(0, 100), 'speed': random.uniform(0.5, 1.5)}
            for _ in range(5)
        ]

    def update(self):
        for cloud in self.clouds:
            cloud['x'] += cloud['speed']
            if cloud['x'] > self.screen_width:
                cloud['x'] = -100
                cloud['y'] = random.randint(0, 100)

    def draw(self, screen):
        for cloud in self.clouds:
            pygame.draw.ellipse(screen, (200, 200, 200), (cloud['x'], cloud['y'], 100, 50))
            pygame.draw.ellipse(screen, (200, 200, 200), (cloud['x'] + 25, cloud['y'] - 25, 100, 50))

class RainAnimation(WeatherAnimation):
    def __init__(self, screen_width, screen_height):
        super().__init__(screen_width, screen_height)
        self.particles = [
            {'x': random.randint(0, screen_width), 'y': random.randint(0, screen_height), 'speed': random.uniform(5, 15)}
            for _ in range(100)
        ]

    def update(self):
        for particle in self.particles:
            particle['y'] += particle['speed']
            if particle['y'] > self.screen_height:
                particle['y'] = 0
                particle['x'] = random.randint(0, self.screen_width)

    def draw(self, screen):
        for particle in self.particles:
            pygame.draw.line(screen, (100, 100, 255), (particle['x'], particle['y']), (particle['x'], particle['y'] + 5), 2)

class SunAnimation(WeatherAnimation):
    def __init__(self, screen_width, screen_height):
        super().__init__(screen_width, screen_height)
        self.angle = 0

    def update(self):
        self.angle += 0.02
        if self.angle > 2 * 3.14159:
            self.angle = 0

    def draw(self, screen):
        x = int(self.screen_width / 2 + 200 * pygame.math.Vector2(1, 0).rotate(self.angle * 180 / 3.14159).x)
        y = int(100 - 50 * pygame.math.Vector2(0, 1).rotate(self.angle * 180 / 3.14159).y)
        pygame.draw.circle(screen, (255, 255, 0), (x, y), 30)

class StormAnimation(WeatherAnimation):
    def __init__(self, screen_width, screen_height):
        super().__init__(screen_width, screen_height)
        self.lightning_timer = 0
        self.show_lightning = False

    def update(self):
        self.lightning_timer += 1
        if self.lightning_timer > 60:
            self.show_lightning = random.choice([True, False])
            self.lightning_timer = 0 if self.show_lightning else self.lightning_timer

    def draw(self, screen):
        if self.show_lightning:
            pygame.draw.polygon(screen, (255, 255, 200), 
                                [(random.randint(0, self.screen_width), 0),
                                 (random.randint(0, self.screen_width), self.screen_height/2),
                                 (random.randint(0, self.screen_width), self.screen_height/2),
                                 (random.randint(0, self.screen_width), self.screen_height)])

class SnowAnimation(WeatherAnimation):
    def __init__(self, screen_width, screen_height):
        super().__init__(screen_width, screen_height)
        self.particles = [
            {'x': random.randint(0, screen_width), 'y': random.randint(0, screen_height), 'speed': random.uniform(1, 3), 'size': random.randint(2, 5)}
            for _ in range(100)
        ]

    def update(self):
        for particle in self.particles:
            particle['y'] += particle['speed']
            particle['x'] += random.uniform(-1, 1)
            if particle['y'] > self.screen_height:
                particle['y'] = 0
                particle['x'] = random.randint(0, self.screen_width)

    def draw(self, screen):
        for particle in self.particles:
            pygame.draw.circle(screen, (255, 255, 255), (int(particle['x']), int(particle['y'])), particle['size'])

class MoonAnimation(WeatherAnimation):
    def __init__(self, screen_width, screen_height):
        super().__init__(screen_width, screen_height)
        self.angle = 3.14159  # Start from the left side

    def update(self):
        self.angle += 0.01
        if self.angle > 3 * 3.14159 / 2:
            self.angle = 3.14159

    def draw(self, screen):
        x = int(self.screen_width / 2 + 300 * pygame.math.Vector2(1, 0).rotate(self.angle * 180 / 3.14159).x)
        y = int(100 - 50 * pygame.math.Vector2(0, 1).rotate(self.angle * 180 / 3.14159).y)
        pygame.draw.circle(screen, (200, 200, 200), (x, y), 25)
        pygame.draw.circle(screen, (0, 0, 0), (x + 5, y), 25)  # Create crescent effect