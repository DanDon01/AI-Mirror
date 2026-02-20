import logging
from config import CONFIG
import time
import traceback

class ModuleManager:
    def __init__(self, initialized_modules=None):
        self.module_visibility = CONFIG.get('module_visibility', {})
        self.logger = logging.getLogger(__name__)
        
        self.modules = {}
        self.enabled_modules = CONFIG.get('enabled_modules', [])
        
        if initialized_modules:
            self.modules = initialized_modules
            self.enabled_modules = list(initialized_modules.keys())
            self.logger.info("Using PRE-INITIALIZED modules from MagicMirror")
            
            # Initialize visibility based on provided modules
            for module_name in self.modules:
                self.module_visibility[module_name] = True
            
            # Check if AIVoiceModule is present and functional
            self.verify_voice_module()
        else:
            self.initialize_modules()

    def verify_voice_module(self):
        """Verify if voice module is working; try alternatives if needed"""
        voice_modules = ['eleven_voice', 'ai_voice']
        
        for module_name in voice_modules:
            if module_name in self.modules:
                try:
                    if module_name == 'eleven_voice' or (hasattr(self.modules[module_name], 'session_ready') and 
                        self.modules[module_name].session_ready):
                        self.logger.info(f"{module_name} is functional - using as primary voice interface")
                        # Hide other voice modules
                        for other_module in voice_modules:
                            if other_module != module_name:
                                self.module_visibility[other_module] = False
                        return
                except Exception as e:
                    self.logger.error(f"{module_name} verification failed: {e}")
                    continue
        
        self.fallback_to_interaction()

    def fallback_to_interaction(self):
        """Activate AIInteractionModule as fallback if AIVoiceModule fails"""
        if 'ai_interaction' in self.modules:
            self.logger.info("Falling back to AIInteractionModule")
            self.module_visibility['ai_voice'] = False
            self.module_visibility['ai_interaction'] = True
        else:
            self.logger.error("No AIInteractionModule available for fallback")

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
        """Initialize modules with priority for AI voice modules"""
        self.logger.info("Initializing modules in priority order")
        
        # Priority order: ai_voice first, then ai_interaction, then others
        priority_modules = ['ai_voice', 'ai_interaction']
        regular_modules = [m for m in self.enabled_modules if m not in priority_modules]
        
        # Try AI voice modules first
        for module_name in priority_modules:
            if module_name in self.enabled_modules and module_name not in self.modules:
                self.initialize_module(module_name)
                if module_name == 'ai_voice' and module_name in self.modules:
                    # If ai_voice succeeds, skip ai_interaction
                    if 'ai_interaction' in self.enabled_modules:
                        self.logger.info("AIVoiceModule initialized successfully - skipping AIInteractionModule")
                        self.enabled_modules.remove('ai_interaction')
                    break
                elif module_name == 'ai_interaction':
                    self.logger.info("Using AIInteractionModule as fallback")
        
        # Initialize regular modules
        for module_name in regular_modules:
            if module_name not in self.modules:
                self.initialize_module(module_name)
        
        self.logger.info("All modules initialized")

    def initialize_module(self, module_name):
        """Initialize a specific module"""
        if module_name not in self.enabled_modules:
            return
        
        config = CONFIG.get(module_name, {})
        if not isinstance(config, dict) or 'class' not in config:
            self.logger.warning(f"No valid config for {module_name}")
            return
        
        try:
            if config['class'] == 'AIVoiceModule':
                from ai_voice_module import AIVoiceModule
                module_class = AIVoiceModule
            elif config['class'] == 'AIInteractionModule':
                from AI_Module import AIInteractionModule
                module_class = AIInteractionModule
            elif config['class'] == 'ElevenVoice':
                from elevenvoice_module import ElevenVoice
                module_class = ElevenVoice
            else:
                module_class = globals().get(config['class'])
            
            if module_class:
                self.logger.info(f"Initializing {module_name}")
                instance = module_class(**config.get('params', {}))
                self.modules[module_name] = instance
                self.module_visibility[module_name] = True
                self.logger.info(f"Successfully initialized {module_name}")
            else:
                self.logger.error(f"Class {config['class']} not found for {module_name}")
        except Exception as e:
            self.logger.error(f"Error initializing {module_name}: {e}")
            self.logger.error(traceback.format_exc())
            if module_name == 'ai_voice':
                self.logger.warning("AIVoiceModule failed - will attempt fallback")

if __name__ == "__main__":
    # Test setup
    logging.basicConfig(level=logging.INFO)
    manager = ModuleManager()
    print(manager.modules)