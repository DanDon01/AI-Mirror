import pygame
import math
import time

class VisualEffects:
    @staticmethod
    def fade_surface(surface, alpha):
        """Apply alpha fade to a surface"""
        surface.set_alpha(alpha)
        return surface
    
    @staticmethod
    def pulse_effect(min_alpha=180, max_alpha=255, speed=0.5):
        """Create a pulsing alpha effect"""
        current_time = time.time()
        # Sine wave oscillation between min and max alpha
        alpha_range = max_alpha - min_alpha
        alpha = min_alpha + alpha_range * (math.sin(current_time * speed) * 0.5 + 0.5)
        return int(alpha)
    
    @staticmethod
    def create_gradient_surface(width, height, start_color, end_color, vertical=True):
        """Create a gradient surface"""
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        
        for i in range(height if vertical else width):
            # Calculate the color at this position
            progress = i / (height if vertical else width)
            current_color = [
                start_color[0] + (end_color[0] - start_color[0]) * progress,
                start_color[1] + (end_color[1] - start_color[1]) * progress,
                start_color[2] + (end_color[2] - start_color[2]) * progress,
                start_color[3] + (end_color[3] - start_color[3]) * progress
            ]
            
            if vertical:
                pygame.draw.line(surface, current_color, (0, i), (width, i))
            else:
                pygame.draw.line(surface, current_color, (i, 0), (i, height))
                
        return surface
    
    @staticmethod
    def draw_rounded_rect(surface, rect, color, radius=15, alpha=255):
        """Draw a rounded rectangle with alpha"""
        rect_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(rect_surface, (*color, alpha), (0, 0, rect.width, rect.height), border_radius=radius)
        surface.blit(rect_surface, rect)
        return rect_surface
    
    @staticmethod
    def create_text_with_shadow(font, text, color, shadow_color=(30, 30, 30), offset=2):
        """Create text with shadow effect"""
        text_surface = font.render(text, True, color)
        shadow_surface = font.render(text, True, shadow_color)
        
        # Create a surface large enough to hold both
        combined = pygame.Surface((text_surface.get_width() + offset, 
                                  text_surface.get_height() + offset), 
                                 pygame.SRCALPHA)
        
        # Blit shadow first, then text
        combined.blit(shadow_surface, (offset, offset))
        combined.blit(text_surface, (0, 0))
        
        return combined 

    def init_module_styles(self, module, styling=None):
        """Initialize consistent styling for a module"""
        if styling is None:
            styling = CONFIG.get('module_styling', {})
        
        fonts = styling.get('fonts', {})
        
        # Initialize fonts
        title_size = fonts.get('title', {}).get('size', FONT_SIZE_TITLE)
        body_size = fonts.get('body', {}).get('size', FONT_SIZE_BODY)
        small_size = fonts.get('small', {}).get('size', FONT_SIZE_SMALL)
        
        module.title_font = pygame.font.SysFont(FONT_NAME, title_size)
        module.body_font = pygame.font.SysFont(FONT_NAME, body_size)
        module.small_font = pygame.font.SysFont(FONT_NAME, small_size)
        
        # Add other common properties
        module.radius = styling.get('radius', DEFAULT_RADIUS)
        module.padding = styling.get('spacing', {}).get('padding', DEFAULT_PADDING)
        module.line_height = styling.get('spacing', {}).get('line_height', DEFAULT_LINE_HEIGHT)
        
        # Set dimensions from config
        module.module_width = CONFIG.get('module_dimensions', {}).get('standard', {}).get('width', 225)
        module.module_height = CONFIG.get('module_dimensions', {}).get('standard', {}).get('height', 200)
        module.header_height = CONFIG.get('module_dimensions', {}).get('standard', {}).get('header_height', 40)
        
        return module 