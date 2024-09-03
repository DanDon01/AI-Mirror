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
        logging.info(f"RetroCharactersModule initialized with spawn_probability: {self.spawn_probability}, fall_speed: {self.fall_speed}, max_active_icons: {self.max_active_icons}")

    def load_icons(self):
        icon_dir = CONFIG.get('retro_characters', {}).get('icon_directory', 'retro_icons')
        if not os.path.exists(icon_dir):
            logging.error(f"Icon directory {icon_dir} does not exist")
            return
        try:
            png_files = [f for f in os.listdir(icon_dir) if f.endswith('.png')]
            if not png_files:
                logging.error(f"No PNG files found in {icon_dir}")
                return
            for filename in png_files:
                icon_path = os.path.join(icon_dir, filename)
                icon_image = pygame.image.load(icon_path)
                icon_image = pygame.transform.scale(icon_image, (self.icon_size, self.icon_size))
                self.icons.append(icon_image)
            logging.info(f"Loaded {len(self.icons)} retro icons from {icon_dir}")
        except Exception as e:
            logging.error(f"Error loading retro icons from {icon_dir}: {e}")

    def update(self):
        if random.random() < self.spawn_probability and len(self.active_icons) < self.max_active_icons:
            new_icon = random.choice(self.icons)
            x_position = random.randint(0, self.screen_width - self.icon_size)
            self.active_icons.append((new_icon, x_position, 0))
            logging.debug(f"Spawned new icon. Active icons: {len(self.active_icons)}")

        # Update positions of active icons
        self.active_icons = [(icon, x, y + self.fall_speed) for icon, x, y in self.active_icons if y < self.screen_height]

    def draw(self, screen):
        for icon, x, y in self.active_icons:
            icon.set_alpha(TRANSPARENCY)
            screen.blit(icon, (x, y))
        logging.debug(f"Drew {len(self.active_icons)} active icons")

    def cleanup(self):
        self.active_icons.clear()  # Clear all active icons
