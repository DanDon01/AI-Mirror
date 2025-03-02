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
import sys
import base64
import select
import struct

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
        
        # Safer approach for audio hardware detection
        # Don't try to check audio devices at init time - defer to when needed
        print("MIRROR DEBUG: 🔍 Deferring audio hardware check until needed")
        
        # Initialize systems
        self.initialize_openai()
        self.load_sound_effects()
        
        # Start background processes
        self.start_websocket_connection()
        
        # Don't use speech_recognition for hotword - we'll use a button-only approach
        # self.initialize_hotword_detection()
        
        # Add this near the start of __init__
        print("MIRROR DEBUG: 🔍 Checking audio device usage:")
        try:
            import subprocess
            result = subprocess.run(["fuser", "-v", "/dev/snd/*"], capture_output=True, text=True)
            print(result.stdout)
            print(result.stderr)
        except Exception as e:
            print(f"MIRROR DEBUG: Could not check audio device usage: {e}")
    
    def initialize_openai(self):
        """Initialize the OpenAI client with the voice API key and check for Realtime API access"""
        try:
            # Try to get the key from config first
            openai_config = self.config.get('openai', {})
            self.api_key = openai_config.get('api_key')
            
            # If no key in config, try loading directly from environment and file
            if not self.api_key:
                import os
                
                # First try environment variable
                self.api_key = os.getenv('OPENAI_VOICE_KEY')
                
                # If still no key, try reading directly from the environment file
                if not self.api_key:
                    try:
                        env_file = '/home/dan/Projects/Variables.env'
                        if os.path.exists(env_file):
                            print(f"MIRROR DEBUG: Attempting to read Voice API key directly from {env_file}")
                            with open(env_file, 'r') as f:
                                for line in f:
                                    if line.strip().startswith('OPENAI_VOICE_KEY='):
                                        self.api_key = line.strip().split('=', 1)[1].strip('"').strip("'")
                                        print(f"MIRROR DEBUG: Successfully loaded Voice API key from file: {self.api_key[:4]}...{self.api_key[-4:] if len(self.api_key) > 8 else ''}")
                                        break
                    except Exception as e:
                        print(f"MIRROR DEBUG: Error reading env file: {e}")
            
            # Check if we have a key now
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
            
            # Set the specific model version to use
            self.realtime_model = 'gpt-4o-realtime-preview-2024-10-01'
            print(f"MIRROR DEBUG: Will use specific realtime model: {self.realtime_model}")
            
            # Try a direct API call to check beta access for this specific model
            try:
                import requests
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                    'OpenAI-Beta': 'realtime=v1'
                }
                
                # Try to get info about this specific model
                model_url = f'https://api.openai.com/v1/models/{self.realtime_model}'
                response = requests.get(model_url, headers=headers)
                
                if response.status_code == 200:
                    # Success - we have access to this model
                    print(f"MIRROR DEBUG: ✅ Confirmed access to realtime model: {self.realtime_model}")
                    self.has_openai_access = True
                    self.set_status("Ready", "Realtime API ready")
                else:
                    # Try WebSocket connection as a fallback - WITHOUT using timeout
                    print(f"MIRROR DEBUG: 🔄 Model API check failed, trying WebSocket connection...")
                    import websocket
                    import threading
                    
                    # Create variables for thread to modify
                    self.ws_test_complete = False
                    self.ws_test_successful = False
                    
                    def on_open(ws):
                        print(f"MIRROR DEBUG: ✅ WebSocket connection to {self.realtime_model} successful!")
                        self.ws_test_successful = True
                        self.ws_test_complete = True
                        ws.close()
                    
                    def on_error(ws, error):
                        print(f"MIRROR DEBUG: ❌ WebSocket connection failed: {error}")
                        self.ws_test_complete = True
                    
                    def on_close(ws, close_status_code, close_msg):
                        self.ws_test_complete = True
                    
                    # Create WebSocket app
                    ws_url = f"wss://api.openai.com/v1/realtime?model={self.realtime_model}"
                    ws_headers = [
                        "Authorization: Bearer " + self.api_key,
                        "OpenAI-Beta: realtime=v1"
                    ]
                    
                    ws = websocket.WebSocketApp(
                        ws_url,
                        header=ws_headers,
                        on_open=on_open,
                        on_error=on_error,
                        on_close=on_close
                    )
                    
                    # Start WebSocket in a thread so we can set our own timeout
                    ws_thread = threading.Thread(target=ws.run_forever)
                    ws_thread.daemon = True
                    ws_thread.start()
                    
                    # Wait for a maximum of 5 seconds
                    timeout = 5
                    start_time = time.time()
                    while not self.ws_test_complete and time.time() - start_time < timeout:
                        time.sleep(0.1)
                    
                    # Set connection flag based on result
                    if self.ws_test_successful:
                        self.has_openai_access = True
                        print("MIRROR DEBUG: ✅ WebSocket test confirmed Realtime API access")
                        self.set_status("Ready", "Realtime API ready (WebSocket)")
                    else:
                        print("MIRROR DEBUG: ❌ Failed to access Realtime API")
                        self.set_status("Error", "No Realtime API access")
                
            except Exception as check_error:
                self.logger.error(f"Failed to check model access: {check_error}")
                print(f"MIRROR DEBUG: ❌ Model access check failed: {check_error}")
                
        except Exception as e:
            self.logger.error(f"OpenAI Voice API initialization error: {e}")
            print(f"MIRROR DEBUG: ❌ Voice API error: {e}")
            self.set_status("Error", f"Voice API error: {str(e)[:30]}")
    
    def start_websocket_connection(self):
        """Initialize WebSocket connection to OpenAI Realtime API with audio streaming"""
        if not self.has_openai_access or not self.api_key:
            self.logger.warning("Cannot start WebSocket - No API key or access")
            return
        
        try:
            import websocket
            import threading
            import json
            import base64
            
            self.logger.info("Initializing WebSocket connection to OpenAI Realtime API")
            print("MIRROR DEBUG: 🔄 Starting WebSocket connection to Realtime API")
            
            # Define connection URL with the realtime model
            self.ws_url = f"wss://api.openai.com/v1/realtime?model={self.realtime_model}"
            print(f"MIRROR DEBUG: Using model: {self.realtime_model} for realtime connection")
            
            # Set up headers with API key and beta flag
            self.ws_headers = [
                f"Authorization: Bearer {self.api_key}",
                "OpenAI-Beta: realtime=v1"
            ]
            
            # Track session state
            self.session_ready = False
            self.response_in_progress = False
            self.audio_stream = None
            self.collected_audio = bytearray()
            
            # Define WebSocket event handlers
            def on_open(ws):
                self.logger.info("WebSocket connection established")
                print("MIRROR DEBUG: ✅ Connected to OpenAI Realtime API")
                # Initial setup happens after session.created
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    event_type = data.get("type", "")
                    
                    # SPECIAL CASE: Completely ignore buffer errors after response is complete
                    if (hasattr(self, 'response_complete') and self.response_complete and 
                        event_type == "error" and "buffer too small" in str(data.get("error", {}).get("message", ""))):
                        print("MIRROR DEBUG: 🔇 Silently ignoring buffer error after response complete")
                        return  # Exit early without logging
                    
                    # Add more detailed debug info
                    print(f"\nMIRROR DEBUG: 📄 WebSocket event: {event_type}")
                    
                    # More detailed event information for specific events
                    if "error" in event_type:
                        error_message = data.get("error", {}).get("message", "Unknown error")
                        error_type = data.get("error", {}).get("type", "unknown")
                        error_code = data.get("error", {}).get("code", "none")
                        print(f"MIRROR DEBUG: 📄 Error details: {error_message}")
                        print(f"MIRROR DEBUG: 📄 Error type: {error_type}, code: {error_code}")
                        print(f"MIRROR DEBUG: 📄 Full error data: {data}")
                    
                    # Track WebSocket states
                    print(f"MIRROR DEBUG: 📄 Current states: recording={self.recording}, processing={self.processing}")
                    print(f"MIRROR DEBUG: 📄 Has response_complete: {hasattr(self, 'response_complete')}")
                    
                    # Handle session lifecycle events
                    if event_type == "session.created":
                        self.session_ready = True
                        self.logger.info("Session created")
                        print("MIRROR DEBUG: ✅ Realtime session established")
                        
                        # Configure the session with initial settings
                        init_event = {
                            "type": "session.update",
                            "session": {
                                "instructions": "You are a helpful assistant running on a Magic Mirror. Be concise but thorough in your responses.",
                                "modalities": ["text", "audio"],  # Enable both text and audio responses
                                "voice": "alloy"  # Use the Alloy voice
                            }
                        }
                        ws.send(json.dumps(init_event))
                        print("MIRROR DEBUG: 📝 Session configured with text and audio responses")
                    
                    elif event_type == "session.updated":
                        self.logger.info("Session updated successfully")
                        print("MIRROR DEBUG: ✓ Session configuration updated")
                    
                    # Handle voice activity detection events
                    elif event_type == "input_audio_buffer.speech_started":
                        if not hasattr(self, 'speech_started'):
                            self.logger.info("Speech detected")
                            print("MIRROR DEBUG: 🎤 User started speaking")
                            self.speech_started = True
                    
                    elif event_type == "input_audio_buffer.speech_stopped":
                        if hasattr(self, 'speech_started'):
                            self.logger.info("Speech ended")
                            print("MIRROR DEBUG: 🛑 User stopped speaking")
                            delattr(self, 'speech_started')
                    
                    # Handle model response events
                    elif event_type == "response.created":
                        if not hasattr(self, 'response_started'):
                            self.logger.info("Response started")
                            print("MIRROR DEBUG: 🧠 Model generating response...")
                            self.response_started = True
                            self.current_response = ""
                    
                    elif event_type == "content_block.delta" and data.get("delta", {}).get("type") == "text_delta":
                        text_delta = data.get("delta", {}).get("text", "")
                        if hasattr(self, 'response_started'):
                            # Add to current response
                            self.current_response += text_delta
                            print(text_delta, end="", flush=True)
                    
                    elif event_type == "response.done" or event_type == "message.complete":
                        print("\nMIRROR DEBUG: ✅ Response complete")
                        print(f"MIRROR DEBUG: 📄 Response complete from event: {event_type}")
                        print(f"MIRROR DEBUG: 📄 Full response data: {data}")
                        
                        # Set a flag to ignore subsequent buffer errors
                        self.response_complete = True
                        print("MIRROR DEBUG: 📄 Set response_complete flag to true")
                        
                        # Clean all audio-related state
                        self.collected_audio = bytearray()
                        if hasattr(self, 'current_audio_buffer'):
                            delattr(self, 'current_audio_buffer')
                        
                        # Reset all states
                        self.recording = False
                        self.processing = False
                        print("MIRROR DEBUG: 📄 Reset recording and processing flags")
                        
                        # Put final response in queue
                        if hasattr(self, 'current_response') and self.current_response:
                            self.response_queue.put({
                                "type": "text",
                                "text": self.current_response,
                                "is_complete": True
                            })
                            self.current_response = ""
                        
                        self.set_status("Ready", "Say 'Mirror' or press SPACE")
                    
                    elif event_type == "error":
                        error_message = data.get("error", {}).get("message", "Unknown error")
                        error_type = data.get("error", {}).get("type", "unknown")
                        error_code = data.get("error", {}).get("code", "none")
                        
                        self.logger.error(f"WebSocket error: {error_message}")
                        print(f"MIRROR DEBUG: ❌ Realtime API error: {error_message}")
                        print(f"MIRROR DEBUG: 📄 Error type: {error_type}, code: {error_code}")
                        print(f"MIRROR DEBUG: 📄 Full error data: {data}")
                        
                        # Reset states on error
                        self.recording = False
                        self.processing = False
                        if hasattr(self, 'response_started'):
                            delattr(self, 'response_started')
                        if hasattr(self, 'speech_started'):
                            delattr(self, 'speech_started')
                        
                        self.set_status("Ready", "Say 'Mirror' or press SPACE")
                    
                    # Add an audio response handler
                    elif event_type == "content_block.delta" and data.get("delta", {}).get("type") == "audio_delta":
                        audio_data = data.get("delta", {}).get("audio", "")
                        if audio_data:
                            try:
                                # Decode and play the audio
                                audio_bytes = base64.b64decode(audio_data)
                                print(f"MIRROR DEBUG: 🔊 Received {len(audio_bytes)} bytes of audio")
                                self.play_audio_chunk(audio_bytes)
                            except Exception as e:
                                print(f"MIRROR DEBUG: ❌ Error playing audio: {e}")
                
                except Exception as e:
                    self.logger.error(f"Error processing WebSocket message: {e}")
                    print(f"MIRROR DEBUG: ❌ Error processing message: {e}")
            
            def on_error(ws, error):
                self.logger.error(f"WebSocket error: {error}")
                print(f"MIRROR DEBUG: ❌ WebSocket error: {error}")
                self.has_openai_access = False
                self.session_ready = False
            
            def on_close(ws, close_status_code, close_msg):
                self.logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
                print(f"MIRROR DEBUG: WebSocket connection closed")
                # Try to reconnect after a delay if we were running
                if self.running:
                    def reconnect():
                        if self.running:
                            print("MIRROR DEBUG: 🔄 Attempting to reconnect WebSocket...")
                            time.sleep(5)  # Wait 5 seconds before reconnecting
                            self.start_websocket_connection()
                    
                    threading.Thread(target=reconnect, daemon=True).start()
            
            # Create WebSocket instance
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                header=self.ws_headers,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Start WebSocket in background thread
            self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            self.ws_thread.start()
            
            self.logger.info("WebSocket connection thread started")
            
            # Initialize audio streaming
            self.initialize_audio_streaming()
            
        except Exception as e:
            self.logger.error(f"Error starting WebSocket connection: {e}")
            print(f"MIRROR DEBUG: ❌ Failed to start WebSocket connection: {e}")
    
    def set_status(self, status, message=None):
        """Update status with logging"""
        self.status = status
        if message:
            self.status_message = message
        self.logger.info(f"Status changed to: {status} - {message}")
    
    def load_sound_effects(self):
        """Load sound effects used by the voice module"""
        try:
            # Initialize pygame mixer if it's not already initialized
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            # Sound effect paths
            sounds_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'sound_effects')
            
            # Sound to play when starting to listen
            listen_sound_path = os.path.join(sounds_dir, 'mirror_listening.mp3')
            self.logger.info(f"Loading sound effect from: {listen_sound_path}")
            
            if os.path.exists(listen_sound_path):
                self.listen_sound = pygame.mixer.Sound(listen_sound_path)
                self.listen_sound.set_volume(0.7)  # Set to a reasonable volume
            else:
                self.logger.warning(f"Listen sound effect file not found: {listen_sound_path}")
                self.listen_sound = None
                
        except Exception as e:
            self.logger.error(f"Error loading sound effects: {e}")
            self.listen_sound = None

    def play_listen_sound(self):
        """Play the listening notification sound"""
        try:
            if hasattr(self, 'listen_sound') and self.listen_sound:
                self.listen_sound.play()
        except Exception as e:
            self.logger.error(f"Error playing listen sound: {e}")
    
    def on_button_press(self):
        """Handle button press (space bar) for voice interaction"""
        try:
            # If we're already recording, stop recording early
            if self.recording:
                self.logger.info("Stopping recording early")
                print("MIRROR DEBUG: 🛑 Stopping recording early due to second button press")
                
                # Set a flag to indicate we're stopping deliberately
                self.stopping_deliberately = True
                
                # Stop the audio stream - this will trigger the commit event
                self.stop_audio_stream()
                
                # Update status
                self.processing = True
                self.set_status("Processing", "Processing your request...")
                return
            
            # If we're processing, don't start a new recording yet
            if self.processing:
                self.logger.info("Still processing previous request")
                print("MIRROR DEBUG: Still processing previous request")
                return
            
            # Start a new recording
            self.stopping_deliberately = False
            self.start_audio_stream()
            
        except Exception as e:
            self.logger.error(f"Button press error: {e}")
            print(f"MIRROR DEBUG: ❌ Button press error: {e}")
    
    def process_voice_input(self):
        """Process voice input using OpenAI Realtime API with proper session handling"""
        if not hasattr(self, 'ws') or not self.has_openai_access or not self.session_ready:
            self.logger.error("WebSocket not ready - cannot process voice")
            print("MIRROR DEBUG: ❌ WebSocket connection not ready")
            self.recording = False
            self.processing = False
            return
        
        try:
            import json
            import time
            
            # Set status
            self.recording = True
            self.set_status("Listening", "Listening via Realtime API...")
            print("MIRROR DEBUG: 🎙️ Listening via Realtime API...")
            
            # Simulate recording audio (you would use actual recording code here)
            time.sleep(2)  # Pretend to record
            
            # For now, use a hardcoded query (would be replaced with actual transcription)
            user_query = "What's the weather like today?"
            print(f"MIRROR DEBUG: 👤 User: {user_query}")
            
            # Switch to processing state
            self.recording = False
            self.processing = True
            self.response_in_progress = True
            self.set_status("Processing", "Processing with Realtime API...")
            
            # First add user message to conversation
            conversation_item = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": user_query,
                        }
                    ]
                }
            }
            
            # Send user input to the conversation
            if hasattr(self, 'ws'):
                self.ws.send(json.dumps(conversation_item))
                print("MIRROR DEBUG: 📤 Added user message to conversation")
                
                # Request response generation
                response_request = {
                    "type": "response.create",
                    "response": {
                        "modalities": ["text"]  # For now just use text
                    }
                }
                
                # Send response request to generate AI reply
                self.ws.send(json.dumps(response_request))
                print("MIRROR DEBUG: 📤 Requested model response")
                
                # Wait for response.done event (handled in on_message)
                timeout = 15  # seconds
                start_time = time.time()
                while self.response_in_progress and time.time() - start_time < timeout:
                    time.sleep(0.1)
                
                if self.response_in_progress:
                    print("MIRROR DEBUG: ⚠️ Response timed out")
                    self.response_in_progress = False
        
        except Exception as e:
            self.logger.error(f"Error in voice processing: {e}")
            print(f"MIRROR DEBUG: ❌ Voice processing error: {e}")
        finally:
            # Reset state if not already done by response handling
            if self.processing:
                self.processing = False
            if self.recording:
                self.recording = False
            self.set_status("Ready", "Say 'Mirror' or press SPACE")
    
    def speak_text(self, text):
        """Convert text to speech"""
        if not text:
            return
        
        try:
            # Create a temporary file for the audio
            temp_file = "response.mp3"
            
            # Create TTS mp3
            tts = gTTS(text=text, lang='en', slow=False)
            tts.save(temp_file)
            
            # Initialize pygame mixer if needed
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            # Load and play the speech
            speech = pygame.mixer.Sound(temp_file)
            speech.set_volume(self.tts_volume)
            
            # Play the speech
            speech.play()
            
            # Wait for it to finish
            pygame.time.wait(int(speech.get_length() * 1000))
            
            # Clean up
            os.remove(temp_file)
            
        except Exception as e:
            self.logger.error(f"Error in TTS: {e}")
    
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
        """Clean up resources including WebSocket connection"""
        self.running = False
        
        # Close WebSocket if it exists
        if hasattr(self, 'ws'):
            try:
                self.ws.close()
                self.logger.info("WebSocket connection closed")
            except Exception as e:
                self.logger.error(f"Error closing WebSocket: {e}")
        
        self.logger.info("Voice module cleanup complete")

    def initialize_audio_streaming(self):
        """Set up audio streaming capabilities directly to WebSocket"""
        try:
            import subprocess
            
            # Check if arecord works with the USB mic - this is just to verify the device exists
            try:
                # Use the exact command that worked in your test
                subprocess.run(["arecord", "-D", "hw:2,0", "-d", "1", "-f", "S16_LE", "-c", "1", "-r", "44100", "/dev/null"], 
                              check=True, stderr=subprocess.PIPE)
                self.mic_device = "hw:2,0"
                print("MIRROR DEBUG: ✅ USB microphone test successful")
            except subprocess.CalledProcessError:
                # Fallback to default device
                self.mic_device = "default" 
                print("MIRROR DEBUG: ⚠️ Using default audio device")
            
            self.has_audio = True
            self.logger.info(f"Audio streaming initialized with device: {self.mic_device}")
            print(f"MIRROR DEBUG: ✅ Audio streaming initialized with device: {self.mic_device}")
            
        except Exception as e:
            self.logger.error(f"Audio initialization error: {e}")
            print(f"MIRROR DEBUG: ❌ Audio initialization error: {e}")
            self.has_audio = False

    def start_audio_stream(self):
        """Start streaming audio using the exact working command"""
        if not hasattr(self, 'session_ready') or not self.session_ready:
            self.logger.error("Cannot start audio stream - WebSocket session not ready")
            return False
        
        try:
            # Reset session state to prevent errors from previous interactions
            if hasattr(self, 'response_complete'):
                delattr(self, 'response_complete')
            
            # Create a new WebSocket session for each interaction
            self.reset_websocket_session()
            
            import threading
            import subprocess
            import base64
            import json
            import time
            import os
            
            # Reset state
            self.recording = True
            self.processing = False
            
            def record_and_stream():
                try:
                    print("MIRROR DEBUG: 🎙️ Starting audio capture")
                    self.set_status("Listening", "Listening via Realtime API...")
                    
                    # Create a unique filename for this recording
                    temp_wav = os.path.join(os.getcwd(), f"recording_{int(time.time())}.wav")
                    
                    # Use the exact command that works in terminal
                    cmd = f"cd {os.getcwd()} && arecord -D hw:2,0 -f S16_LE -c 1 -r 44100 -d 5 {temp_wav}"
                    print(f"MIRROR DEBUG: 🎙️ Running: {cmd}")
                    
                    # Run in the same environment as terminal
                    process = subprocess.run(
                        cmd,
                        shell=True,
                        env={
                            'PATH': os.environ['PATH'],
                            'HOME': os.environ['HOME'],
                            'USER': os.environ['USER'],
                            'SHELL': os.environ.get('SHELL', '/bin/bash')
                        }
                    )
                    
                    if process.returncode == 0 and os.path.exists(temp_wav):
                        print(f"MIRROR DEBUG: ✅ Recording successful: {temp_wav}")
                        
                        # Read the WAV file
                        with open(temp_wav, 'rb') as f:
                            # Skip WAV header (44 bytes)
                            f.seek(44)
                            audio_data = f.read()
                        
                        # Clean up the temporary file
                        try:
                            os.unlink(temp_wav)
                        except Exception as e:
                            print(f"MIRROR DEBUG: ⚠️ Could not delete temp file: {e}")
                        
                        # Stream to API in chunks
                        chunk_size = 16384
                        total_sent = 0
                        
                        for i in range(0, len(audio_data), chunk_size):
                            chunk = audio_data[i:i+chunk_size]
                            audio_b64 = base64.b64encode(chunk).decode('ascii')
                            
                            if hasattr(self, 'ws'):
                                audio_event = {
                                    "type": "input_audio_buffer.append",
                                    "audio": audio_b64
                                }
                                self.ws.send(json.dumps(audio_event))
                                total_sent += len(chunk)
                                print(f"MIRROR DEBUG: 📤 Sent {len(chunk)} bytes to API")
                        
                        # Send commit event
                        if hasattr(self, 'ws') and total_sent > 0:
                            commit_event = {
                                "type": "input_audio_buffer.commit"
                            }
                            self.ws.send(json.dumps(commit_event))
                            print(f"MIRROR DEBUG: ✅ Audio committed to API ({total_sent} bytes total)")
                            
                            # Update status
                            self.recording = False
                            self.processing = True
                            self.set_status("Processing", "Processing your request...")
                        else:
                            print("MIRROR DEBUG: ⚠️ No audio was sent to API")
                            self.recording = False
                            self.set_status("Error", "No audio captured")
                    else:
                        print(f"MIRROR DEBUG: ❌ Recording failed")
                        self.recording = False
                        self.set_status("Error", "Recording failed")
                
                except Exception as e:
                    self.logger.error(f"Audio recording error: {e}")
                    print(f"MIRROR DEBUG: ❌ Audio recording error: {str(e)}")
                    self.set_status("Error", f"Audio error: {str(e)[:30]}")
                    self.recording = False
                    self.processing = False
            
            # Start the recording thread
            self.audio_thread = threading.Thread(target=record_and_stream)
            self.audio_thread.daemon = True
            self.audio_thread.start()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting audio stream: {e}")
            print(f"MIRROR DEBUG: ❌ Failed to start audio stream: {e}")
            self.set_status("Error", "Failed to start audio")
            self.recording = False
            return False

    def stop_audio_stream(self):
        """Stop the audio recording process and clear states"""
        try:
            # Mark that we're stopping recording
            self.logger.info("Stopping recording early")
            print("MIRROR DEBUG: 🛑 Stopping recording early due to second button press")
            
            # Set recording to false to stop the main thread's processing
            self.recording = False
            self.stopping_deliberately = True
            
            # Terminate the recording process if it exists
            if hasattr(self, 'recording_process') and self.recording_process:
                try:
                    self.recording_process.terminate()
                    self.recording_process.wait(timeout=1)
                    self.logger.info("Recording process terminated")
                    print("MIRROR DEBUG: 🎙️ Recording process terminated")
                except Exception as e:
                    self.logger.error(f"Error terminating recording: {e}")
                    # Force kill if needed
                    try:
                        self.recording_process.kill()
                    except:
                        pass
            
            # Let the audio processing thread finish naturally
            # DO NOT send additional commit events here
            
            self.logger.info("Audio streaming stopped")
            print("MIRROR DEBUG: 🎙️ Audio streaming stopped")
            
            # Update status to processing - the audio thread will handle sending data to API
            self.processing = True
            self.set_status("Processing", "Processing your request...")
            
        except Exception as e:
            self.logger.error(f"Error stopping audio stream: {e}")
            print(f"MIRROR DEBUG: ❌ Error stopping audio stream: {e}")

    def play_audio_chunk(self, audio_bytes):
        """Play an audio chunk received from the API using system player for reliability"""
        try:
            import tempfile
            import os
            import subprocess
            
            # Create a temporary file for the audio chunk
            temp_filename = f"/tmp/mirror_audio_{int(time.time())}.wav"
            print(f"MIRROR DEBUG: 🔊 Writing {len(audio_bytes)} bytes to {temp_filename}")
            
            # Write WAV header (improved version)
            with open(temp_filename, 'wb') as temp_file:
                # WAV header
                temp_file.write(b'RIFF')
                temp_file.write(struct.pack('<I', 36 + len(audio_bytes)))
                temp_file.write(b'WAVE')
                
                # Format chunk
                temp_file.write(b'fmt ')
                temp_file.write(struct.pack('<I', 16))  # Subchunk1Size
                temp_file.write(struct.pack('<H', 1))   # PCM format
                temp_file.write(struct.pack('<H', 1))   # Mono channel
                temp_file.write(struct.pack('<I', 24000))  # Sample rate
                temp_file.write(struct.pack('<I', 24000 * 2))  # ByteRate
                temp_file.write(struct.pack('<H', 2))   # BlockAlign
                temp_file.write(struct.pack('<H', 16))  # BitsPerSample
                
                # Data chunk
                temp_file.write(b'data')
                temp_file.write(struct.pack('<I', len(audio_bytes)))
                temp_file.write(audio_bytes)
            
            # Play audio using system commands - more reliable than pygame
            print(f"MIRROR DEBUG: 🔊 Playing audio with system player")
            
            # Use aplay command - standard on Linux
            try:
                process = subprocess.Popen(["aplay", temp_filename], 
                                          stdout=subprocess.PIPE, 
                                          stderr=subprocess.PIPE)
                # Don't wait for it to finish - let it play in background
                print("MIRROR DEBUG: 🔊 Audio playback started")
                
                # Schedule file cleanup after a few seconds
                def cleanup_audio_file():
                    time.sleep(5)  # Wait for playback to likely finish
                    try:
                        os.remove(temp_filename)
                        print(f"MIRROR DEBUG: 🧹 Cleaned up audio file: {temp_filename}")
                    except:
                        pass
                
                # Start cleanup thread
                cleanup_thread = threading.Thread(target=cleanup_audio_file)
                cleanup_thread.daemon = True
                cleanup_thread.start()
                
            except Exception as play_err:
                print(f"MIRROR DEBUG: ⚠️ Could not play with aplay: {play_err}")
                # Try alternative players if available
                try:
                    os.system(f"paplay {temp_filename}")
                except:
                    pass
            
        except Exception as e:
            self.logger.error(f"Error playing audio chunk: {e}")
            print(f"MIRROR DEBUG: ❌ Error playing audio chunk: {e}")

    def initialize_hotword_detection(self):
        """Set up hotword detection in the background"""
        try:
            # Import required libraries
            import speech_recognition as sr
            import threading
            
            # Create a recognizer
            self.hotword_recognizer = sr.Recognizer()
            
            # Configure the microphone for hotword detection
            # Try to get a microphone index
            self.hotword_mic = None
            try:
                # Find an available microphone
                for index, name in enumerate(sr.Microphone.list_microphone_names()):
                    if 'usb' in name.lower() or 'mic' in name.lower():
                        print(f"MIRROR DEBUG: ✅ Found microphone for hotword detection: {index} - {name}")
                        self.hotword_mic = sr.Microphone(device_index=index)
                        break
            
            except Exception as e:
                self.logger.warning(f"Failed to find specific microphone: {e}")
                print(f"MIRROR DEBUG: Using default microphone for hotword detection (error: {e})")
                self.hotword_mic = sr.Microphone()
            
            # Start hotword detection in a background thread
            self.hotword_thread = threading.Thread(target=self.hotword_detection_loop)
            self.hotword_thread.daemon = True
            self.hotword_thread.start()
            
            self.logger.info("Hotword detection initialized")
            print("MIRROR DEBUG: ✅ Hotword detection initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize hotword detection: {e}")
            print(f"MIRROR DEBUG: ❌ Failed to initialize hotword detection: {e}")

    def hotword_detection_loop(self):
        """Listen for the 'mirror' hotword in the background"""
        while self.running:
            try:
                # Skip if already recording/processing
                if self.recording or self.processing:
                    time.sleep(0.5)
                    continue
                    
                # Use the microphone to listen for the hotword
                with self.hotword_mic as source:
                    try:
                        # Adjust for ambient noise
                        self.hotword_recognizer.adjust_for_ambient_noise(source, duration=0.5)
                        
                        # Listen with short timeout
                        audio = self.hotword_recognizer.listen(source, timeout=1, phrase_time_limit=3)
                        
                        # Try to recognize with Google's API
                        text = self.hotword_recognizer.recognize_google(audio).lower()
                        self.logger.debug(f"Heard hotword check: {text}")
                        
                        # Check if the hotword is in the text
                        if "mirror" in text:
                            self.logger.info(f"Hotword detected: {text}")
                            print(f"MIRROR DEBUG: 🎤 Hotword detected: '{text}'")
                            self.on_button_press()
                            # Add delay to prevent re-triggering
                            time.sleep(2)
                
                    except sr.UnknownValueError:
                        # Normal - no speech detected
                        pass
                    except sr.RequestError:
                        # Google API issue - back off
                        time.sleep(2)
                    except Exception as e:
                        if "timed out" not in str(e):
                            self.logger.warning(f"Hotword listener error: {e}")
                            time.sleep(0.5)
            
            except Exception as e:
                self.logger.warning(f"Hotword loop error: {e}")
                time.sleep(1)
                
            # Small pause before next attempt
            time.sleep(0.1)

    def test_hotword_detection(self):
        """Simple test of hotword detection capability"""
        try:
            import speech_recognition as sr
            
            print("MIRROR DEBUG: 🎙️ Testing hotword detection...")
            print("MIRROR DEBUG: 🎙️ Available microphones:")
            
            for index, name in enumerate(sr.Microphone.list_microphone_names()):
                print(f"MIRROR DEBUG:   {index}: {name}")
            
            # Use index 2 (same as your working audio device)
            test_mic = sr.Microphone(device_index=2)
            
            print("MIRROR DEBUG: 🎙️ Recording a 3-second test...")
            with test_mic as source:
                recognizer = sr.Recognizer()
                recognizer.adjust_for_ambient_noise(source)
                print("MIRROR DEBUG: 🎙️ Speak now...")
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=3)
            
            print("MIRROR DEBUG: 🎙️ Recognizing...")
            try:
                text = recognizer.recognize_google(audio)
                print(f"MIRROR DEBUG: ✅ Recognized: '{text}'")
                return True
            except sr.UnknownValueError:
                print("MIRROR DEBUG: ❓ Could not understand audio")
                return False
            except sr.RequestError as e:
                print(f"MIRROR DEBUG: ❌ Recognition error: {e}")
                return False
            
        except Exception as e:
            print(f"MIRROR DEBUG: ❌ Hotword test error: {e}")
            return False

    def reset_websocket_session(self):
        """Create a fresh WebSocket session"""
        try:
            # Close existing WebSocket if any
            if hasattr(self, 'ws') and self.ws:
                try:
                    self.ws.close()
                    print("MIRROR DEBUG: 🔄 Closed existing WebSocket")
                except:
                    pass
            
            # Reset session
            self.session_ready = False
            print("MIRROR DEBUG: 🔄 Resetting WebSocket session")
            
            # Start a new WebSocket connection
            self.start_websocket_connection()
            
            # Wait for session to be ready
            timeout = 5
            start_time = time.time()
            while not self.session_ready and time.time() - start_time < timeout:
                time.sleep(0.1)
            
            if self.session_ready:
                print("MIRROR DEBUG: ✅ New WebSocket session ready")
                return True
            else:
                print("MIRROR DEBUG: ⚠️ Timed out waiting for new session")
                return False
        
        except Exception as e:
            print(f"MIRROR DEBUG: ❌ Error resetting WebSocket session: {e}")
            return False
