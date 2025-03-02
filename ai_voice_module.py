import asyncio
import websockets
import json
import os
import pygame
import logging
import threading
import speech_recognition as sr
from gtts import gTTS
from queue import Queue
from config import CONFIG
import time
import openai
import numpy as np
from openai import OpenAI

DEFAULT_MAX_TOKENS = 250

class AIVoiceModule:
    """Module for OpenAI's realtime voice API"""
    
    def __init__(self, config):
        self.logger = logging.getLogger("AI_Voice")
        self.logger.info("Initializing AI Voice Module (Realtime API)")
        
        # Store configuration
        self.config = config or {}
        
        # Initialize properties
        self.status = "Initializing"
        self.status_message = "Starting voice systems..."
        self.recording = False
        self.processing = False
        self.has_openai_access = False
        self.response_queue = Queue()
        self.running = True
        
        # Setup API configuration
        openai_config = self.config.get('openai', {})
        self.api_key = openai_config.get('voice_api_key') or openai_config.get('api_key')
        self.model = openai_config.get('model', 'gpt-4o')
        
        # Audio settings
        audio_config = self.config.get('audio', {})
        self.tts_volume = audio_config.get('tts_volume', 0.8)
        
        # Initialize systems
        self.initialize_openai()
        self.load_sound_effects()
        
        # Start background processes
        self.start_websocket_connection()
    
    def initialize_openai(self):
        """Initialize the OpenAI client with the voice API key"""
        try:
            if not self.api_key:
                self.logger.error("No OpenAI Voice API key provided")
                print("MIRROR DEBUG: ❌ No OpenAI Voice API key available")
                self.set_status("Error", "No Voice API key")
                return
            
            # Create OpenAI client with voice API key
            openai.api_key = self.api_key
            self.client = OpenAI(api_key=self.api_key)
            
            # Test connection
            print("MIRROR DEBUG: 🔄 Testing OpenAI Voice API connection...")
            response = self.client.models.list()
            if response:
                model_names = [model.id for model in response]
                
                # Check if we have access to required models
                required_models = ['gpt-4o', 'whisper-1', 'tts-1']
                missing_models = [m for m in required_models if not any(m in name for name in model_names)]
                
                if missing_models:
                    self.logger.warning(f"Missing required models: {missing_models}")
                    print(f"MIRROR DEBUG: ⚠️ Voice API missing models: {missing_models}")
                    self.set_status("Limited", "Limited model access")
                else:
                    self.logger.info("OpenAI Voice API connection successful")
                    print("MIRROR DEBUG: ✅ OpenAI Voice API connection successful")
                    self.has_openai_access = True
                    self.set_status("Ready", "Voice API ready")
            else:
                self.logger.warning("OpenAI Voice API connection test failed")
                print("MIRROR DEBUG: ⚠️ OpenAI Voice API test failed")
                self.set_status("Error", "Voice API connection failed")
        except Exception as e:
            self.logger.error(f"OpenAI Voice API initialization error: {e}")
            print(f"MIRROR DEBUG: ❌ Voice API error: {e}")
            self.set_status("Error", f"Voice API error: {str(e)[:30]}")
    
    def start_websocket_connection(self):
        """Start the WebSocket connection for realtime audio"""
        self.logger.info("WebSocket connection would be initialized here")
        # This is where you would initialize the websocket connection
        # to OpenAI's realtime audio API when it becomes available
        pass
    
    def set_status(self, status, message=None):
        """Update status with logging"""
        self.status = status
        if message:
            self.status_message = message
        self.logger.info(f"Status changed to: {status} - {message}")
    
    def load_sound_effects(self):
        """Load necessary sound effects"""
        self.sound_effects = {}
        try:
            # Initialize pygame mixer if needed
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            # Load listening sound effect
            sound_paths = CONFIG.get('sound_effects_path', [])
            if not isinstance(sound_paths, list):
                sound_paths = [sound_paths]
            
            # Add default paths
            sound_paths.extend([
                '/home/dan/Projects/ai_mirror/assets/sound_effects',
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'sound_effects')
            ])
            
            # Try to load the sound effect
            for base_path in sound_paths:
                if not base_path:
                    continue
                
                listening_file = os.path.join(base_path, 'mirror_listening.mp3')
                if os.path.exists(listening_file):
                    self.logger.info(f"Loading sound effect from: {listening_file}")
                    self.sound_effects['mirror_listening'] = pygame.mixer.Sound(listening_file)
                    break
            
            # Create fallback sound if needed
            if 'mirror_listening' not in self.sound_effects:
                self.create_fallback_sound()
                
        except Exception as e:
            self.logger.error(f"Error loading sound effects: {e}")
            self.create_fallback_sound()
    
    def create_fallback_sound(self):
        """Create a simple beep sound"""
        try:
            # Create a simple sine wave beep
            sample_rate = 22050
            duration = 0.3
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            beep = np.sin(2 * np.pi * 440 * t) * 0.5
            
            # Convert to 16-bit integers
            beep = (beep * 32767).astype(np.int16)
            
            # Create a stereo sound
            if pygame.mixer.get_init():
                beep_sound = pygame.sndarray.make_sound(np.column_stack([beep, beep]))
                self.sound_effects['mirror_listening'] = beep_sound
                self.logger.info("Created fallback beep sound")
        except Exception as e:
            self.logger.error(f"Failed to create fallback sound: {e}")
    
    def on_button_press(self):
        """Handle activation (space bar or hotword)"""
        if self.recording or self.processing:
            self.logger.info("Already recording or processing")
            print("MIRROR DEBUG: Already in a session - ignoring activation")
            return
        
        self.logger.info("Voice activation triggered")
        print("MIRROR DEBUG: 🎤 Voice activation triggered (Realtime API)")
        
        # Set status and play sound
        self.set_status("Listening", "Listening for voice...")
        if 'mirror_listening' in self.sound_effects:
            self.sound_effects['mirror_listening'].play()
        
        # Start voice input thread
        self.recording = True
        threading.Thread(target=self.process_voice_input, daemon=True).start()
    
    def process_voice_input(self):
        """Process voice input using realtime API"""
        try:
            # This simulates the realtime voice processing
            # In real implementation, this would connect to the 
            # OpenAI realtime voice API via WebSockets
            
            # Simulate waiting for voice input
            self.set_status("Listening", "Speak now...")
            print("MIRROR DEBUG: 🎙️ Realtime API listening for voice input...")
            time.sleep(2)  # Simulate listening
            
            # Simulate processing
            self.recording = False
            self.processing = True
            self.set_status("Processing", "Processing your request...")
            print("MIRROR DEBUG: 🧠 Realtime API processing voice...")
            time.sleep(1)  # Simulate processing
            
            # Simulate response
            response = "This is a simulated response from the OpenAI Realtime Voice API."
            self.set_status("Responding", "Speaking response...")
            print(f"MIRROR DEBUG: 🔊 Realtime API response: {response}")
            
            # Add response to queue
            self.response_queue.put(('voice', {
                'user_text': 'Simulated user input',
                'ai_response': response
            }))
            
        except Exception as e:
            self.logger.error(f"Error in realtime voice processing: {e}")
            print(f"MIRROR DEBUG: ❌ Realtime voice error: {e}")
            
        finally:
            self.recording = False
            self.processing = False
            self.set_status("Ready", "Say 'Mirror' or press SPACE")
    
    def update(self):
        """Regular update for background processes"""
        pass
    
    def draw(self, screen, position):
        """Draw the module UI"""
        try:
            import pygame
            
            # Extract position
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 225) 
                height = position.get('height', 200)
            else:
                x, y = position
                width, height = 225, 200
            
            # Draw background
            pygame.draw.rect(screen, (30, 30, 40), (x, y, width, height))
            pygame.draw.rect(screen, (50, 50, 150), (x, y, width, height), 2)  # Blue border for realtime
            
            # Initialize fonts
            if not hasattr(self, 'font'):
                self.font = pygame.font.Font(None, 24)
                self.title_font = pygame.font.Font(None, 32)
            
            # Draw title
            title = self.title_font.render("Voice AI (Realtime)", True, (150, 150, 255))
            screen.blit(title, (x + 10, y + 10))
            
            # Draw status
            status_text = self.font.render(f"Status: {self.status}", True, (200, 200, 200))
            screen.blit(status_text, (x + 10, y + 50))
            
            # Draw message if available
            if self.status_message:
                msg = self.status_message
                if len(msg) > 30:
                    msg = msg[:27] + "..."
                msg_text = self.font.render(msg, True, (200, 200, 200))
                screen.blit(msg_text, (x + 10, y + 80))
            
            # Draw indicators
            # API status
            api_color = (0, 255, 0) if self.has_openai_access else (255, 0, 0)
            pygame.draw.circle(screen, api_color, (x + 20, y + 120), 8)
            api_text = self.font.render("Voice API", True, (200, 200, 200))
            screen.blit(api_text, (x + 35, y + 112))
            
            # Recording indicator
            if self.recording:
                # Pulsing red circle
                pulse = int(128 + 127 * np.sin(pygame.time.get_ticks() / 200))
                rec_color = (255, pulse, pulse)
                pygame.draw.circle(screen, rec_color, (x + 20, y + 150), 8)
                rec_text = self.font.render("Recording", True, rec_color)
                screen.blit(rec_text, (x + 35, y + 142))
            
            # Processing indicator
            if self.processing:
                # Pulsing blue circle
                pulse = int(128 + 127 * np.sin(pygame.time.get_ticks() / 300))
                proc_color = (pulse, pulse, 255)
                pygame.draw.circle(screen, proc_color, (x + 20, y + 180), 8)
                proc_text = self.font.render("Processing", True, proc_color)
                screen.blit(proc_text, (x + 35, y + 172))
                
        except Exception as e:
            self.logger.error(f"Error drawing Voice module: {e}")
    
    def handle_event(self, event):
        """Handle pygame events"""
        try:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    if not self.recording and not self.processing:
                        self.on_button_press()
                elif event.key == pygame.K_ESCAPE:
                    if self.recording:
                        self.recording = False
                        self.set_status("Ready", "Recording canceled")
        except Exception as e:
            self.logger.error(f"Error handling event: {e}")
    
    def cleanup(self):
        """Clean up resources"""
        self.running = False
        self.logger.info("Voice module cleanup complete")
