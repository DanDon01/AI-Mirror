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
        """Recalculate positions for side-by-side layout with clear center"""
        # Log dimensions
        logging.info(f"Screen dimensions: {self.screen_width}x{self.screen_height}")
        
        # Define layout parameters
        top_margin = 60
        side_margin = 40
        module_height = 180
        module_width = int(self.screen_width * 0.25)  # 25% of screen width
        center_gap = self.screen_width - (module_width * 2) - (side_margin * 2)
        vertical_spacing = 30
        
        # Calculate vertical positions (3 rows)
        row_y = [
            top_margin + 60,  # First row (after clock)
            top_margin + module_height + vertical_spacing + 60,  # Second row
            top_margin + (module_height + vertical_spacing) * 2 + 60  # Third row
        ]
        
        # Calculate horizontal positions (left and right sides)
        left_x = side_margin
        right_x = self.screen_width - side_margin - module_width
        
        # Assign module positions
        
        # Clock spans the top
        self.module_positions['clock'] = {
            'x': 0,
            'y': 5,
            'width': self.screen_width,
            'height': 50
        }
        
        # Left side modules
        self.module_positions['weather'] = {
            'x': left_x,
            'y': row_y[0],
            'width': module_width,
            'height': module_height
        }
        
        self.module_positions['stocks'] = {
            'x': left_x,
            'y': row_y[1],
            'width': module_width,
            'height': module_height
        }
        
        self.module_positions['calendar'] = {
            'x': left_x,
            'y': row_y[2],
            'width': module_width,
            'height': module_height
        }
        
        # Right side modules
        self.module_positions['fitbit'] = {
            'x': right_x,
            'y': row_y[0],
            'width': module_width,
            'height': module_height
        }
        
        # Placeholder for additional right-side module
        self.module_positions['placeholder'] = {
            'x': right_x,
            'y': row_y[1],
            'width': module_width,
            'height': module_height
        }
        
        # AI module on right side bottom
        self.module_positions['ai_module'] = {
            'x': right_x,
            'y': row_y[2],
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
            logging.info(f"{module_name}: (x={pos['x']}, y={pos['y']}), size={pos['width']}x{pos['height']}")

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
