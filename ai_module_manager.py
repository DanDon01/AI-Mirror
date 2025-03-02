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
from ai_voice_module import AIVoiceModule as RealtimeModule

class AIModuleManager:
    def __init__(self, config=None):
        # Set up basic attributes
        self.logger = logging.getLogger(__name__)
        self.config = config or {}
        self.active_module = None
        self.response_queue = Queue()
        self.status = "Initializing"
        self.status_message = "Starting AI systems..."
        
        # Extract the AI configuration specifically
        ai_config = config.get('config', {})
        
        # Store original config for module initialization
        self.ai_config = ai_config
        
        # Check if realtime is enabled - get from the correct location
        self.realtime_enabled = ai_config.get('realtime_enabled', True)  # Default to enabled
        self.logger.info(f"Realtime API enabled: {self.realtime_enabled}")
        
        # Initialize AI modules
        try:
            # First try to initialize the realtime module if enabled
            self.realtime_module = None
            self.standard_module = None
            
            if self.realtime_enabled:
                try:
                    self.logger.info("Attempting to initialize Realtime Voice API module")
                    print("MIRROR DEBUG: 🔄 Initializing Realtime Voice API module")
                    
                    # Import here to avoid circular imports
                    from ai_voice_module import AIVoiceModule
                    
                    # Make sure config includes OPENAI_VOICE_KEY
                    voice_config = dict(ai_config)
                    if 'openai' in voice_config:
                        # FIXED: Directly get the voice key from the environment
                        import os
                        voice_api_key = os.getenv('OPENAI_VOICE_KEY')
                        if voice_api_key:
                            # Directly set the API key instead of relying on nested get
                            voice_config['openai']['api_key'] = voice_api_key
                            print(f"MIRROR DEBUG: Using voice API key from environment for realtime module: {voice_api_key[:4]}...{voice_api_key[-4:]}")
                        else:
                            print("MIRROR DEBUG: ⚠️ Could not find OPENAI_VOICE_KEY in environment for realtime module")
                    
                    # Initialize the voice module
                    self.realtime_module = AIVoiceModule(voice_config)
                    
                    # Test if it's working
                    if self.realtime_module.has_openai_access:
                        self.logger.info("✅ Realtime Voice API module initialized successfully")
                        print("MIRROR DEBUG: ✅ Realtime Voice API available - using as primary")
                        self.active_module = self.realtime_module
                        self.status = "Ready (Realtime Voice)"
                    else:
                        self.logger.warning("Realtime Voice API module failed to connect")
                        print("MIRROR DEBUG: ⚠️ Realtime Voice API initialization failed")
                        # We'll try the standard module next
                except Exception as e:
                    self.logger.warning(f"Failed to initialize Realtime Voice API module: {e}")
                    print(f"MIRROR DEBUG: ⚠️ Error initializing Realtime Voice: {e}")
            
            # Initialize standard module as fallback (or primary if realtime disabled)
            try:
                self.logger.info("Initializing standard OpenAI module")
                print("MIRROR DEBUG: 🔄 Initializing standard OpenAI module")
                
                # Import the standard module
                from AI_Module import AIInteractionModule
                
                # Make sure config uses standard API key
                standard_config = dict(ai_config)
                if 'openai' in standard_config:
                    # Use the standard API key
                    standard_config['openai']['api_key'] = standard_config['openai'].get('api_key')
                
                # Initialize the standard module
                self.standard_module = AIInteractionModule(standard_config)
                
                # If we don't have an active module yet, use the standard one
                if not self.active_module and self.standard_module.has_openai_access:
                    self.logger.info("Using standard OpenAI module")
                    print("MIRROR DEBUG: ✅ Standard OpenAI API available")
                    self.active_module = self.standard_module
                    self.status = "Ready (Standard API)"
                
            except Exception as e:
                self.logger.error(f"Failed to initialize standard OpenAI module: {e}")
                print(f"MIRROR DEBUG: ❌ Error initializing standard module: {e}")
            
            # If we have an active module, we're ready
            if self.active_module:
                self.status_message = "Say 'Mirror' or press SPACE to activate"
                print(f"MIRROR DEBUG: ✅ Using {self.active_module.__class__.__name__} as primary AI module")
            else:
                self.logger.error("No AI modules could be initialized")
                self.status = "Error"
                self.status_message = "AI systems unavailable"
                print("MIRROR DEBUG: ❌ No AI modules available")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize any AI module: {e}")
            self.active_module = None
            self.status = "Error"
            self.status_message = "AI systems unavailable"
            print(f"MIRROR DEBUG: ❌ AI module initialization failed: {e}")
        
        # Start monitoring thread to check module health
        self.running = True
        self.monitor_thread = threading.Thread(target=self.monitor_modules)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
    
    def monitor_modules(self):
        """Monitor module health and switch if needed"""
        while self.running:
            try:
                # If active module is realtime but not working, switch to standard
                if (self.active_module == self.realtime_module and 
                    (not self.realtime_module or not self.realtime_module.has_openai_access)):
                    self.logger.warning("Realtime module lost connection - switching to standard")
                    print("MIRROR DEBUG: ⚠️ Realtime module unavailable - switching to standard")
                    if self.standard_module and self.standard_module.has_openai_access:
                        self.active_module = self.standard_module
                        self.status = "Ready (Standard API)"
                
                # If active module is standard but realtime becomes available, switch back
                elif (self.active_module == self.standard_module and self.realtime_enabled and
                      self.realtime_module and self.realtime_module.has_openai_access):
                    self.logger.info("Realtime module now available - switching back")
                    print("MIRROR DEBUG: ✅ Realtime module now available - switching back")
                    self.active_module = self.realtime_module
                    self.status = "Ready (Realtime Voice)"
                
                # Update status message from active module
                if self.active_module:
                    if hasattr(self.active_module, 'status'):
                        self.status = self.active_module.status
                    if hasattr(self.active_module, 'status_message'):
                        self.status_message = self.active_module.status_message
            
            except Exception as e:
                self.logger.error(f"Error in module monitor: {e}")
            
            # Check every 5 seconds
            time.sleep(5)
    
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
        if hasattr(self, 'standard_module'):
            self.standard_module.cleanup()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1.0)
    
    def on_button_press(self):
        """Delegate button press to active module"""
        print(f"MIRROR DEBUG: AIModuleManager received button press. Active module: {self.active_module}")
        if self.active_module and hasattr(self.active_module, 'on_button_press'):
            self.logger.info("Delegating button press to active module")
            self.active_module.on_button_press()
        else:
            self.logger.error("No active module or module doesn't support button press")
            print(f"MIRROR DEBUG: ❌ Button press failed - no active AI module. Active module: {self.active_module}")
            
            # Debug attributes of active module
            if self.active_module:
                print(f"Module methods: {[method for method in dir(self.active_module) if not method.startswith('_')]}") 