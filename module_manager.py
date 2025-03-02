import logging
from config import CONFIG

class ModuleManager:
    def __init__(self):
        self.module_visibility = CONFIG.get('module_visibility', {})
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"ModuleManager initialized with visibility states: {self.module_visibility}")

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