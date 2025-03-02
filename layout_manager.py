import pygame
from config import CONFIG, FONT_NAME
import logging
from visual_effects import VisualEffects
from config import draw_module_background_fallback

class LayoutManager:
    def __init__(self, screen_width, screen_height):
        # Get configured screen size from CONFIG
        config_screen = CONFIG.get('current_monitor', {})
        config_width = config_screen.get('width')
        config_height = config_screen.get('height')
        
        # Use config values if available (override passed parameters)
        if config_width and config_height:
            logging.info(f"Using screen dimensions from config: {config_width}x{config_height}")
            self.screen_width = config_width
            self.screen_height = config_height
        else:
            logging.info(f"Using passed screen dimensions: {screen_width}x{screen_height}")
            self.screen_width = screen_width
            self.screen_height = screen_height
        
        self.layout = CONFIG['layout']
        self.scale = CONFIG['screen']['scale']
        self.module_positions = {}
        self.calculate_positions()

        # Initialize visual effects in __init__
        self.effects = VisualEffects()

    def calculate_positions(self):
        """Recalculate positions with even narrower modules to fit screen"""
        # Log dimensions to see what we're working with
        logging.info(f"Screen dimensions: {self.screen_width}x{self.screen_height}")
        
        # Get module dimensions from config
        standard_dims = CONFIG.get('module_styling', {}).get('module_dimensions', {}).get('standard', {})
        module_height = standard_dims.get('height', 200)
        module_width = standard_dims.get('width', 225)
        
        # Use spacing from config
        padding = CONFIG.get('module_styling', {}).get('spacing', {}).get('padding', 10)
        side_margin = padding * 2  # Or define in config
        
        # Force narrower modules for very small displays
        # Assume minimum 700px width display
        module_width = min(int((self.screen_width - (3 * side_margin)) / 2), 250)
        
        # Check if we need to adjust again for very narrow screens
        if module_width * 2 + 3 * side_margin > self.screen_width:
            module_width = (self.screen_width - (3 * side_margin)) // 2
            logging.info(f"Forced module width to {module_width}px for narrow screen")
        
        # Calculate vertical positions (3 rows)
        row_y = [
            padding + 50,  # First row (after clock)
            padding + module_height + 30 + 50,  # Second row
            padding + (module_height + 30) * 2 + 50  # Third row
        ]
        
        # Calculate horizontal positions
        left_x = side_margin
        right_x = self.screen_width - side_margin - module_width
        
        # Log the calculated positions for debugging
        logging.info(f"Left edge: {left_x}, Right edge: {right_x}, Module width: {module_width}")
        logging.info(f"Screen width check: right edge({right_x}) + module width({module_width}) = {right_x + module_width}")
        
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
        
        # Skip placeholder module if screen is too narrow
        if right_x + module_width <= self.screen_width - 10:
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
        font = pygame.font.SysFont(FONT_NAME, fonts['title']['size'])
        title_text = font.render(title, True, fonts['title']['color'])
        text_x = pos['x'] + (pos['width'] - title_text.get_width()) // 2
        screen.blit(title_text, (text_x, pos['y'] + 2))

        try:
            self.effects.draw_rounded_rect(screen, (pos['x'], pos['y'], pos['width'], pos['height']), bg_style['content']['color'], radius=10, alpha=0)
            self.effects.draw_rounded_rect(screen, (pos['x'], pos['y'], pos['width'], title_height), bg_style['title']['color'], radius=10, alpha=0)
        except:
            draw_module_background_fallback(screen, pos['x'], pos['y'], pos['width'], pos['height'], pos['y'] + 2)

        return (pos['x'], pos['y'] + title_height)
