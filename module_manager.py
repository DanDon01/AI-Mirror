import logging
from config import CONFIG
import time

class ModuleManager:
    def __init__(self, initialized_modules=None):
        self.module_visibility = CONFIG.get('module_visibility', {})
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"ModuleManager initialized with visibility states: {self.module_visibility}")
        
        # Store already initialized modules if provided
        self.initialized_modules = initialized_modules or {}
        
        # Skip additional initialization if modules were provided
        if not initialized_modules:
            self.initialize_modules()

    def handle_command(self, command):
        """Handle show/hide commands for modules"""
        action = command['action']
        module = command['module']
        
        if module in self.module_visibility:
            self.module_visibility[module] = (action == 'show')
            self.logger.info(f"{module} module visibility set to {self.module_visibility[module]}")
            return True
        
        self.logger.warning(f"Unknown module: {module}")
        return False

    def is_module_visible(self, module_name):
        """Check if a module should be visible"""
        is_visible = self.module_visibility.get(module_name, True)
        self.logger.debug(f"Checking visibility for {module_name}: {is_visible}")
        return is_visible

    def get_visible_modules(self):
        """Get list of currently visible modules"""
        return [module for module, visible in self.module_visibility.items() if visible]

    def show_module(self, module_name):
        """Show a specific module"""
        if module_name in self.module_visibility:
            self.module_visibility[module_name] = True
            self.logger.info(f"Showed module: {module_name}")
            return True
        return False

    def hide_module(self, module_name):
        """Hide a specific module"""
        if module_name in self.module_visibility:
            self.module_visibility[module_name] = False
            self.logger.info(f"Hid module: {module_name}")
            return True
        return False

    def set_module_visibility(self, module_name, is_visible):
        """Set visibility of a specific module"""
        if module_name in self.module_visibility:
            self.module_visibility[module_name] = is_visible
            self.logger.info(f"Set {module_name} visibility to {is_visible}")
        else:
            self.logger.warning(f"Cannot set visibility - module {module_name} not found")

    def initialize_modules(self):
        """Initialize all modules in the correct order for optimal performance"""
        print("MIRROR DEBUG: 🔄 Initializing modules in priority order")
        
        # Separate modules into regular and AI modules
        regular_modules = []
        ai_modules = []
        
        for module_name in self.modules:
            # Check if this is an AI module (typically has more resource usage)
            if 'ai_' in module_name.lower() or module_name.lower() == 'voice':
                ai_modules.append(module_name)
            else:
                regular_modules.append(module_name)
        
        # Load regular modules first
        for module_name in regular_modules:
            if module_name in self.enabled_modules:
                print(f"MIRROR DEBUG: 🔄 Initializing regular module: {module_name}")
                self.initialize_module(module_name)
        
        # Then load AI modules after a brief delay
        print("MIRROR DEBUG: 🕒 Waiting before initializing AI modules...")
        time.sleep(2)  # Short delay to let other modules stabilize
        
        for module_name in ai_modules:
            if module_name in self.enabled_modules:
                print(f"MIRROR DEBUG: 🔄 Initializing AI module: {module_name}")
                self.initialize_module(module_name)
        
        print("MIRROR DEBUG: ✅ All modules initialized")

    def initialize_module(self, module_name):
        """Initialize a specific module"""
        if module_name in self.modules:
            config = self.modules[module_name]
            if isinstance(config, dict) and 'class' in config:
                try:
                    # Dynamically import if needed
                    if config['class'] == 'AIInteractionModule':
                        from AI_Module import AIInteractionModule
                        module_class = AIInteractionModule
                    elif config['class'] == 'AIVoiceModule':
                        from ai_voice_module import AIVoiceModule
                        module_class = AIVoiceModule
                    else:
                        # Try to get it from globals
                        import sys
                        module_class = getattr(sys.modules['__main__'], config['class'], None)
                        
                    if module_class:
                        # Initialize the module
                        return module_class(**config.get('params', {}))
                    else:
                        self.logger.error(f"Could not find class: {config['class']}")
                except Exception as e:
                    self.logger.error(f"Error initializing module {module_name}: {e}")
            
            return None