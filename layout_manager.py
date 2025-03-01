import pygame
from config import CONFIG
import logging

class LayoutManager:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.layout = CONFIG['layout']
        self.scale = CONFIG['screen']['scale']
        self.module_positions = {}
        self.calculate_positions()

    def calculate_positions(self):
        """Recalculate all module positions based on screen dimensions"""
        padding = self.layout.get('screen_padding', 20)
        sections = self.layout.get('sections', {
            'top': 5,
            'upper': 20,
            'middle': 40,
            'bottom': 60
        })
        
        # Debug output to see actual screen dimensions
        logging.info(f"Screen dimensions: {self.screen_width}x{self.screen_height}")
        
        # Calculate standard module dimensions with safer defaults
        std_width = int(self.screen_width * 0.25)  # 25% of screen width
        std_height = int(self.screen_height * 0.15)  # 15% of screen height
        large_height = int(self.screen_height * 0.25)  # 25% of screen height
        
        # Safety margin to prevent modules from being off-screen
        safety_margin = 50
        right_edge = self.screen_width - std_width - padding
        if right_edge > (self.screen_width - safety_margin):
            right_edge = self.screen_width - std_width - safety_margin
        
        bottom_edge = self.screen_height - std_height - padding
        if bottom_edge > (self.screen_height - safety_margin):
            bottom_edge = self.screen_height - std_height - safety_margin
        
        # Define module regions with improved positioning
        self.module_positions = {
            'clock': {
                'x': (self.screen_width - std_width) // 2,
                'y': padding + int(self.screen_height * sections.get('top', 5) / 100),
                'width': std_width,
                'height': std_height
            },
            'weather': {
                'x': padding,
                'y': padding + int(self.screen_height * sections.get('upper', 20) / 100),
                'width': std_width,
                'height': large_height
            },
            'stocks': {
                'x': min(right_edge, self.screen_width - std_width - padding),
                'y': padding + int(self.screen_height * sections.get('upper', 20) / 100),
                'width': std_width,
                'height': large_height
            },
            'calendar': {
                'x': padding,
                'y': min(bottom_edge, padding + int(self.screen_height * sections.get('bottom', 60) / 100)),
                'width': std_width,
                'height': std_height
            },
            'fitbit': {
                'x': min(right_edge, self.screen_width - std_width - padding),
                'y': min(bottom_edge, padding + int(self.screen_height * sections.get('bottom', 60) / 100)),
                'width': std_width,
                'height': std_height
            },
            'ai_module': {
                'x': (self.screen_width - std_width) // 2,
                'y': min(self.screen_height - std_height - padding, int(self.screen_height * 0.8)),
                'width': std_width,
                'height': std_height
            },
            'retro_characters': {
                'x': 0,
                'y': 0,
                'width': self.screen_width,
                'height': self.screen_height
            }
        }
        
        # Log the calculated positions
        logging.info(f"Calculated module positions:")
        for module_name, pos in self.module_positions.items():
            logging.info(f"{module_name}: {pos}")
        
        # Apply scaling to all dimensions
        scale = self.scale if hasattr(self, 'scale') and self.scale else 1.0
        for module in self.module_positions.values():
            module['x'] = int(module['x'] * scale)
            module['y'] = int(module['y'] * scale)
            module['width'] = int(module['width'] * scale)
            module['height'] = int(module['height'] * scale)

    def get_module_position(self, module_name):
        """Get the position for a specific module"""
        # Default positions if not configured
        default_positions = {
            'clock': {'x': 10, 'y': 10},
            'weather': {'x': 10, 'y': 100},
            'stocks': {'x': 10, 'y': 300},
            'calendar': {'x': 10, 'y': 500},
            'fitbit': {'x': self.screen_width - 210, 'y': 500},
            'retro_characters': {'x': 0, 'y': 0},  # Full screen overlay
            'ai_module': {'x': 10, 'y': self.screen_height - 100}
        }
        
        # First check configured positions
        if hasattr(self, 'module_positions') and module_name in self.module_positions:
            return self.module_positions[module_name]
        
        # Fall back to defaults
        if module_name in default_positions:
            logging.warning(f"Using default position for {module_name}")
            return default_positions[module_name]
        
        # Last resort - top left corner with a warning
        logging.warning(f"No position defined for {module_name} - using top left corner")
        return {'x': 10, 'y': 10}

    def draw_module_background(self, screen, module_name, title):
        pos = self.module_positions.get(module_name)
        if not pos:
            return

        # Get styling from config
        bg_style = self.layout['backgrounds']
        fonts = self.layout['fonts']

        # Draw content background
        bg_surface = pygame.Surface((pos['width'], pos['height']))
        bg_surface.fill(bg_style['content']['color'])
        bg_surface.set_alpha(bg_style['content']['alpha'])
        screen.blit(bg_surface, (pos['x'], pos['y']))

        # Draw title bar
        title_height = int((fonts['title']['size'] + 10) * self.scale)
        title_surface = pygame.Surface((pos['width'], title_height))
        title_surface.fill(bg_style['title']['color'])
        title_surface.set_alpha(bg_style['title']['alpha'])
        screen.blit(title_surface, (pos['x'], pos['y']))

        # Draw title text
        font = pygame.font.SysFont('Arial', fonts['title']['size'])
        title_text = font.render(title, True, fonts['title']['color'])
        text_x = pos['x'] + (pos['width'] - title_text.get_width()) // 2
        screen.blit(title_text, (text_x, pos['y'] + 2))

        return (pos['x'], pos['y'] + title_height)
