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
        """Recalculate module positions for portrait orientation"""
        # Log actual screen dimensions
        logging.info(f"Screen dimensions: {self.screen_width}x{self.screen_height}")
        
        # Simple portrait-mode layout with fixed spacing
        top_margin = 50
        side_margin = 50
        module_height = 180
        module_width = self.screen_width - (side_margin * 2)
        spacing = 20
        
        # Calculate positions for each module in portrait orientation
        current_y = top_margin
        
        # Clock at top
        self.module_positions['clock'] = {
            'x': side_margin,
            'y': current_y,
            'width': module_width,
            'height': module_height
        }
        current_y += module_height + spacing
        
        # Weather below clock
        self.module_positions['weather'] = {
            'x': side_margin,
            'y': current_y,
            'width': module_width,
            'height': module_height
        }
        current_y += module_height + spacing
        
        # Stocks below weather
        self.module_positions['stocks'] = {
            'x': side_margin,
            'y': current_y,
            'width': module_width,
            'height': module_height
        }
        current_y += module_height + spacing
        
        # Fitbit below stocks
        self.module_positions['fitbit'] = {
            'x': side_margin,
            'y': current_y,
            'width': module_width,
            'height': module_height
        }
        current_y += module_height + spacing
        
        # Calendar below fitbit
        self.module_positions['calendar'] = {
            'x': side_margin,
            'y': current_y,
            'width': module_width,
            'height': module_height
        }
        current_y += module_height + spacing
        
        # AI module at bottom
        self.module_positions['ai_module'] = {
            'x': side_margin,
            'y': self.screen_height - module_height - top_margin,
            'width': module_width,
            'height': module_height
        }
        
        # Retro characters is full screen
        self.module_positions['retro_characters'] = {
            'x': 0,
            'y': 0,
            'width': self.screen_width,
            'height': self.screen_height
        }
        
        # Log calculated positions
        for module_name, pos in self.module_positions.items():
            logging.info(f"{module_name}: (x={pos['x']}, y={pos['y']})")

    def get_module_position(self, module_name):
        """Get the position for a specific module, ensuring proper return format"""
        # First check configured positions
        if hasattr(self, 'module_positions') and module_name in self.module_positions:
            position = self.module_positions[module_name]
            
            # Ensure position is a dictionary with x/y keys
            if isinstance(position, dict) and 'x' in position and 'y' in position:
                return position
            # Handle tuple format (x, y)
            elif isinstance(position, tuple) and len(position) == 2:
                return {'x': position[0], 'y': position[1]}
        
        # Fall back to defaults
        default_positions = {
            'clock': {'x': 10, 'y': 10},
            'weather': {'x': 10, 'y': 100},
            'stocks': {'x': 10, 'y': 300},
            'calendar': {'x': 10, 'y': 500},
            'fitbit': {'x': self.screen_width - 210, 'y': 500},
            'retro_characters': {'x': 0, 'y': 0},
            'ai_module': {'x': 10, 'y': self.screen_height - 100}
        }
        
        if module_name in default_positions:
            return default_positions[module_name]
        
        # Last resort - top left corner
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
