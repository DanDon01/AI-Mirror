import logging
import importlib
import threading
import time
import pygame
from queue import Queue
import os
import sys

# Import both modules
from AI_Module import AIInteractionModule as FallbackModule
from ai_voice_module import AIInteractionModule as RealtimeModule

class AIModuleManager:
    def __init__(self, config=None):
        # Set up basic attributes
        self.logger = logging.getLogger(__name__)
        self.config = config or {}
        self.active_module = None
        self.response_queue = Queue()
        self.status = "Initializing"
        self.status_message = "Starting AI systems..."
        
        # Check if realtime is enabled
        self.realtime_enabled = config.get('ai_interaction', {}).get('realtime_enabled', False)
        
        # Initialize AI module
        try:
            if self.realtime_enabled:
                self.logger.info("Attempting to initialize Realtime API module")
                
                try:
                    self.realtime_module = RealtimeModule(self.config)
                    if hasattr(self.realtime_module, 'websocket') and self.realtime_module.websocket:
                        self.logger.info("Realtime API module initialized successfully")
                        self.active_module = self.realtime_module
                        self.status = "Ready (Realtime)"
                        self.status_message = "Say 'Mirror' to activate"
                    else:
                        raise Exception("Failed to connect to Realtime API")
                except Exception as e:
                    self.logger.warning(f"Realtime API module failed to connect: {e}")
                    self.active_module = None
                
            if not self.active_module:
                self.logger.info("Using standard GPT-4 module")
                self.fallback_module = FallbackModule(self.config)
                self.active_module = self.fallback_module
                self.status = "Ready (GPT-4)"
                self.status_message = "Say 'Mirror' to activate"
            
        except Exception as e:
            self.logger.error(f"Failed to initialize any AI module: {e}")
            self.active_module = None
        
        # Start monitoring thread to check module health
        self.running = True
        self.monitor_thread = threading.Thread(target=self.monitor_modules)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
    
    def monitor_modules(self):
        """Monitor the health of modules and switch if necessary"""
        while self.running:
            try:
                # If using realtime module and it's having issues, switch to fallback
                if hasattr(self, 'realtime_module') and self.active_module == self.realtime_module:
                    if (hasattr(self.realtime_module, 'status') and 
                        "error" in self.realtime_module.status.lower()):
                        self.logger.warning("Realtime module error detected, switching to fallback")
                        try:
                            if not hasattr(self, 'fallback_module'):
                                self.fallback_module = FallbackModule(self.config)
                            self.active_module = self.fallback_module
                            self.status = "Ready (Fallback)"
                            self.status_message = "Say 'Mirror' to activate"
                        except Exception as e:
                            self.logger.error(f"Failed to initialize fallback module: {e}")
                            self.status = "Error"
                            self.status_message = "AI systems unavailable"
                            self.active_module = None
                
                # Forward any responses from the active module to our queue
                if self.active_module and hasattr(self.active_module, 'response_queue'):
                    while not self.active_module.response_queue.empty():
                        item = self.active_module.response_queue.get()
                        self.response_queue.put(item)
            
            except Exception as e:
                self.logger.error(f"Error in module monitor: {e}")
            
            time.sleep(1)
    
    def handle_event(self, event):
        """Forward events to the active module"""
        if self.active_module:
            self.active_module.handle_event(event)
    
    def update(self):
        """Update the active module"""
        if self.active_module:
            self.active_module.update()
            
            # Update our status based on active module
            if hasattr(self.active_module, 'status'):
                self.status = self.active_module.status
            if hasattr(self.active_module, 'status_message'):
                self.status_message = self.active_module.status_message
    
    def draw(self, screen, position):
        """Draw the active module's UI"""
        if self.active_module:
            self.active_module.draw(screen, position)
        else:
            # Draw error message if no module is active
            font = pygame.font.Font(None, 36)
            text = font.render(f"AI Status: {self.status}", True, (200, 200, 200))
            screen.blit(text, position)
            if self.status_message:
                message_text = font.render(self.status_message, True, (200, 200, 200))
                screen.blit(message_text, (position[0], position[1] + 40))
    
    def cleanup(self):
        """Clean up resources"""
        self.running = False
        if hasattr(self, 'realtime_module'):
            self.realtime_module.cleanup()
        if hasattr(self, 'fallback_module'):
            self.fallback_module.cleanup()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1.0) 