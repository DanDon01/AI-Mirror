import pygame
import random
import os
import logging
from config import CONFIG, COLOR_FONT_DEFAULT, TRANSPARENCY

class RetroCharactersModule:
    def __init__(self, screen_size):
        self.icons = []
        self.screen_width, self.screen_height = screen_size
        self.icon_size = CONFIG.get('retro_characters', {}).get('icon_size', 64)
        self.load_icons()
        self.active_icons = []
        self.spawn_probability = CONFIG.get('retro_characters', {}).get('spawn_probability', 0.01)
        self.fall_speed = CONFIG.get('retro_characters', {}).get('fall_speed', 2)
        self.max_active_icons = CONFIG.get('retro_characters', {}).get('max_active_icons', 10)

    def load_icons(self):
        icon_dir = CONFIG.get('retro_characters', {}).get('icon_directory', 'retro_icons')
        try:
            for filename in os.listdir(icon_dir):
                if filename.endswith('.png'):
                    icon_path = os.path.join(icon_dir, filename)
                    icon_image = pygame.image.load(icon_path)
                    icon_image = pygame.transform.scale(icon_image, (self.icon_size, self.icon_size))
                    self.icons.append(icon_image)
            logging.info(f"Loaded {len(self.icons)} retro icons")
        except Exception as e:
            logging.error(f"Error loading retro icons: {e}")

    def update(self):
        # Randomly decide to add a new icon
        if random.random() < self.spawn_probability and len(self.active_icons) < self.max_active_icons:
            new_icon = random.choice(self.icons)
            x_position = random.randint(0, self.screen_width - self.icon_size)
            self.active_icons.append((new_icon, x_position, 0))  # Start at top of the screen

        # Update positions of active icons
        self.active_icons = [(icon, x, y + self.fall_speed) for icon, x, y in self.active_icons if y < self.screen_height]

    def draw(self, screen):
        for icon, x, y in self.active_icons:
            icon.set_alpha(TRANSPARENCY)
            screen.blit(icon, (x, y))

    def cleanup(self):
        self.active_icons.clear()  # Clear all active icons
