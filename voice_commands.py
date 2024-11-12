import logging
from enum import Enum

class CommandType(Enum):
    SHOW = "show"
    HIDE = "hide"
    UNKNOWN = "unknown"

class ModuleCommand:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Dictionary mapping keywords to module names
        self.module_keywords = {
            'clock': ['clock', 'time'],
            'weather': ['weather', 'temperature', 'forecast'],
            'stocks': ['stocks', 'market', 'shares'],
            'calendar': ['calendar', 'events', 'schedule'],
            'fitbit': ['fitbit', 'health', 'steps'],
            'retro': ['retro', 'characters', 'icons']
        }
        
        # Action keywords
        self.show_keywords = ['show', 'display', 'enable', 'turn on']
        self.hide_keywords = ['hide', 'remove', 'disable', 'turn off']

    def parse_command(self, text):
        """Parse text to determine command type and target module"""
        text = text.lower()
        self.logger.debug(f"Parsing command: {text}")

        # Determine action type
        command_type = CommandType.UNKNOWN
        for keyword in self.show_keywords:
            if keyword in text:
                command_type = CommandType.SHOW
                break
        for keyword in self.hide_keywords:
            if keyword in text:
                command_type = CommandType.HIDE
                break

        # Find target module
        target_module = None
        for module, keywords in self.module_keywords.items():
            if any(keyword in text for keyword in keywords):
                target_module = module
                break

        if command_type != CommandType.UNKNOWN and target_module:
            self.logger.info(f"Command parsed: {command_type.value} {target_module}")
            return {
                'action': command_type.value,
                'module': target_module
            }
        
        return None