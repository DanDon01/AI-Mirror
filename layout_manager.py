import pygame
from config import CONFIG

class LayoutManager:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.layout = CONFIG['layout']
        self.scale = CONFIG['screen']['scale']
        self.module_positions = {}
        self.calculate_positions()

    def calculate_positions(self):
        padding = self.layout['screen_padding']
        sections = self.layout['sections']
        sizes = self.layout['module_sizes']

        # Calculate standard module dimensions
        std_width = int(self.screen_width * sizes['standard']['width'] / 100)
        std_height = int(self.screen_height * sizes['standard']['height'] / 100)
        large_height = int(self.screen_height * sizes['large']['height'] / 100)

        # Define module regions with new layout system
        self.module_positions = {
            'clock': {
                'x': (self.screen_width - std_width) // 2,
                'y': int(self.screen_height * sections['top'] / 100),
                'width': std_width,
                'height': std_height
            },
            'weather': {
                'x': padding,
                'y': int(self.screen_height * sections['upper'] / 100),
                'width': std_width,
                'height': large_height
            },
            'stocks': {
                'x': self.screen_width - std_width - padding,
                'y': int(self.screen_height * sections['upper'] / 100),
                'width': std_width,
                'height': large_height
            },
            'calendar': {
                'x': padding,
                'y': int(self.screen_height * sections['bottom'] / 100),
                'width': std_width,
                'height': std_height
            },
            'fitbit': {
                'x': self.screen_width - std_width - padding,
                'y': int(self.screen_height * sections['bottom'] / 100),
                'width': std_width,
                'height': std_height
            },
            'ai_module': {
                'x': (self.screen_width - std_width) // 2,
                'y': int(self.screen_height * 0.8),  # Position near bottom
                'width': std_width,
                'height': std_height
            }
        }

        # Apply scaling to all dimensions
        for module in self.module_positions.values():
            module['x'] = int(module['x'] * self.scale)
            module['y'] = int(module['y'] * self.scale)
            module['width'] = int(module['width'] * self.scale)
            module['height'] = int(module['height'] * self.scale)

    def get_module_position(self, module_name):
        return self.module_positions.get(module_name, None)

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
