import pygame
import random
import os
import logging
import math
from config import CONFIG, COLOR_FONT_DEFAULT, TRANSPARENCY

class RetroCharactersModule:
    def __init__(self, screen_size, icon_size=64, icon_directory='assets/retro_icons', spawn_probability=0.01, fall_speed=1, max_active_icons=10, rotation_speed=1):
        self.icons = []
        self.screen_width, self.screen_height = screen_size
        self.icon_size = icon_size
        self.icon_directory = icon_directory
        self.load_icons()
        self.active_icons = []
        self.spawn_probability = spawn_probability
        self.fall_speed = fall_speed
        self.max_active_icons = max_active_icons
        self.rotation_speed = rotation_speed
        logging.info(f"RetroCharactersModule initialized with spawn_probability: {self.spawn_probability}, fall_speed: {self.fall_speed}, max_active_icons: {self.max_active_icons}")

    def load_icons(self):
        if not os.path.exists(self.icon_directory):
            logging.error(f"Icon directory {self.icon_directory} does not exist")
            return
        try:
            png_files = [f for f in os.listdir(self.icon_directory) if f.endswith('.png')]
            if not png_files:
                logging.error(f"No PNG files found in {self.icon_directory}")
                return
            for filename in png_files:
                icon_path = os.path.join(self.icon_directory, filename)
                icon_image = pygame.image.load(icon_path)
                icon_image = pygame.transform.scale(icon_image, (self.icon_size, self.icon_size))
                self.icons.append(icon_image)
            logging.info(f"Loaded {len(self.icons)} retro icons from {self.icon_directory}")
        except Exception as e:
            logging.error(f"Error loading retro icons from {self.icon_directory}: {e}")

    def update(self):
        if not self.icons:
            logging.warning("No icons loaded, skipping update")
            return
        if random.random() < self.spawn_probability and len(self.active_icons) < self.max_active_icons:
            new_icon = random.choice(self.icons)
            x_position = random.randint(0, self.screen_width - self.icon_size)
            self.active_icons.append((new_icon, x_position, 0, 0))  # Added 0 for initial rotation angle
            logging.debug(f"Spawned new icon. Total active icons: {len(self.active_icons)}")

        # Update positions and rotation angles of active icons
        self.active_icons = [(icon, x, y + self.fall_speed, angle + self.rotation_speed) 
                             for icon, x, y, angle in self.active_icons if y < self.screen_height]
        
        if len(self.active_icons) > 0:
            logging.debug(f"Active icons: {len(self.active_icons)}")

    def draw(self, screen):
        for icon, x, y, angle in self.active_icons:
            # Rotate the icon
            rotated_icon = pygame.transform.rotate(icon, angle)
            # Get the rect of the rotated image
            rect = rotated_icon.get_rect()
            # Set the center of the rect to the icon's position
            rect.center = (x + self.icon_size // 2, y + self.icon_size // 2)
            # Set transparency
            rotated_icon.set_alpha(TRANSPARENCY)
            # Draw the rotated icon
            screen.blit(rotated_icon, rect)

    def cleanup(self):
        self.active_icons.clear()  # Clear all active icons
