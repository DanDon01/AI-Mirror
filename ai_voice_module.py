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
                    
                    # Log received event
                    self.logger.debug(f"Received event: {event_type}")
                    
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
                                "modalities": ["text", "audio"]  # Enable both text and audio
                            }
                        }
                        ws.send(json.dumps(init_event))
                        print("MIRROR DEBUG: 📝 Session configured with text and audio modalities")
                    
                    elif event_type == "session.updated":
                        self.logger.info("Session updated successfully")
                        print("MIRROR DEBUG: ✓ Session configuration updated")
                    
                    # Handle voice activity detection events
                    elif event_type == "input_audio_buffer.speech_started":
                        self.logger.info("Speech detected")
                        print("MIRROR DEBUG: 🎤 User started speaking")
                        self.speaking = True
                    
                    elif event_type == "input_audio_buffer.speech_stopped":
                        self.logger.info("Speech ended")
                        print("MIRROR DEBUG: 🛑 User stopped speaking")
                        self.speaking = False
                    
                    # Handle model response events
                    elif event_type == "response.created":
                        self.logger.info("Response started")
                        print("MIRROR DEBUG: 🧠 Model generating response...")
                    
                    elif event_type == "response.text.delta":
                        delta = data.get("delta", {}).get("text", "")
                        # Accumulate text deltas for display
                        print(f"{delta}", end="", flush=True)
                    
                    elif event_type == "response.audio.delta":
                        # Handle audio chunks from the model
                        audio_chunk = data.get("delta", {}).get("audio", "")
                        if audio_chunk:
                            # Decode base64 audio
                            try:
                                audio_bytes = base64.b64decode(audio_chunk)
                                # Play audio directly (implementation varies)
                                self.play_audio_chunk(audio_bytes)
                            except Exception as e:
                                self.logger.error(f"Error playing audio: {e}")
                    
                    elif event_type == "response.done":
                        # Response is complete
                        self.response_in_progress = False
                        self.logger.info("Response complete")
                        print("\nMIRROR DEBUG: ✅ Response complete")
                        
                        # Reset state
                        self.processing = False
                        self.set_status("Ready", "Say 'Mirror' or press SPACE")
                    
                    elif event_type == "error":
                        error_message = data.get("error", {}).get("message", "Unknown error")
                        self.logger.error(f"WebSocket error: {error_message}")
                        print(f"MIRROR DEBUG: ❌ Realtime API error: {error_message}")
                    
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
        """Handle button press or hotword activation"""
        if self.recording or self.processing:
            self.logger.info("Already processing audio")
            return
        
        if not self.session_ready:
            self.logger.warning("Session not ready")
            print("MIRROR DEBUG: ⚠️ Session not ready")
            return
        
        try:
            # Play activation sound
            if hasattr(self, 'sound_effects') and 'mirror_listening' in self.sound_effects:
                self.sound_effects['mirror_listening'].play()
            
            # Set status
            self.set_status("Listening", "Listening via Realtime API...")
            print("MIRROR DEBUG: 🎙️ Listening via Realtime API...")
            
            # Start audio streaming
            success = self.start_audio_stream()
            
            if not success:
                self.set_status("Error", "Failed to start audio")
                return
            
            # The rest happens in callbacks triggered by voice activity detection
            
        except Exception as e:
            self.logger.error(f"Error starting voice input: {e}")
            print(f"MIRROR DEBUG: ❌ Error starting voice input: {e}")
            self.set_status("Error", f"Input error: {str(e)[:30]}")
    
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
        """Set up audio streaming capabilities with a real USB microphone using ALSA directly"""
        try:
            import subprocess
            import base64
            
            # Test if arecord is available
            try:
                subprocess.run(["which", "arecord"], check=True, capture_output=True)
                print("MIRROR DEBUG: ✅ Found arecord utility")
            except subprocess.CalledProcessError:
                raise Exception("arecord utility not found - please install ALSA tools")
            
            # Get device info using arecord -l
            print("MIRROR DEBUG: 🎙️ Available audio devices (ALSA):")
            devices_output = subprocess.check_output(["arecord", "-l"]).decode("utf-8")
            print(devices_output)
            
            # Use the working device that you confirmed
            self.alsa_device = "hw:2,0"  # Based on your working arecord command
            
            # Let's check if this device is valid
            try:
                test_process = subprocess.run(
                    ["arecord", "-D", self.alsa_device, "-d", "1", "-f", "S16_LE", "-c", "1", "-r", "16000", "/dev/null"],
                    check=True, 
                    capture_output=True
                )
                print(f"MIRROR DEBUG: ✅ Successfully tested recording with device {self.alsa_device}")
            except subprocess.CalledProcessError as e:
                print(f"MIRROR DEBUG: ⚠️ Device test failed: {e}")
                print(f"Error output: {e.stderr.decode('utf-8')}")
                # Try to use default device instead
                self.alsa_device = "default"
                print(f"MIRROR DEBUG: Falling back to default ALSA device")
            
            # Audio format parameters - match arecord settings
            self.format = "S16_LE"  # 16-bit signed little endian
            self.channels = 1       # Mono
            self.rate = 16000       # 16kHz sampling rate
            self.audio_buffer = bytearray()
            
            # Mark audio as initialized
            self.has_audio = True
            self.logger.info(f"ALSA audio streaming initialized with device: {self.alsa_device}")
            print(f"MIRROR DEBUG: ✅ ALSA audio streaming initialized with device: {self.alsa_device}")
            
        except Exception as e:
            self.logger.error(f"Audio streaming initialization error: {e}")
            print(f"MIRROR DEBUG: ❌ Audio streaming error: {e}")
            self.has_audio = False

    def start_audio_stream(self):
        """Start streaming audio from the USB microphone to the WebSocket using ALSA directly"""
        if not self.has_audio or not self.session_ready:
            self.logger.error("Cannot start audio stream - not initialized")
            return False
        
        try:
            import threading
            import subprocess
            import io
            import base64
            import json
            import time
            
            # Reset state
            self.audio_buffer = bytearray()
            self.speaking = False
            self.recording = True
            
            # Define thread function to capture and stream audio
            def alsa_stream_thread():
                try:
                    print(f"MIRROR DEBUG: 🎙️ Starting ALSA audio capture with device {self.alsa_device}")
                    self.set_status("Listening", "Listening via Realtime API...")
                    
                    # Create arecord process - stream to stdout
                    cmd = [
                        "arecord",
                        "-D", self.alsa_device,
                        "-f", self.format,
                        "-c", str(self.channels),
                        "-r", str(self.rate),
                        "--buffer-size=4096",
                        "--period-size=1024",
                        "--max-file-time", "10"  # Max 10 seconds per recording
                    ]
                    
                    # Start the recording process
                    self.audio_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    
                    # Check if process started successfully
                    if self.audio_process.poll() is not None:
                        # Process already exited - check stderr
                        error = self.audio_process.stderr.read().decode('utf-8')
                        print(f"MIRROR DEBUG: ❌ arecord failed to start: {error}")
                        self.set_status("Error", "Failed to start recording")
                        self.recording = False
                        return
                    
                    # Set timeout to stop after 10 seconds max
                    start_time = time.time()
                    max_time = 10  # 10 seconds max
                    chunk_size = 4096  # Read in 4K chunks
                    
                    print("MIRROR DEBUG: ✅ Audio recording started")
                                        
                    # Read and stream audio in chunks
                    while self.recording and (time.time() - start_time) < max_time:
                        # Read a chunk of audio data
                        audio_chunk = self.audio_process.stdout.read(chunk_size)
                        
                        # If we got data, send it
                        if audio_chunk and len(audio_chunk) > 0:
                            # Add to buffer
                            self.audio_buffer.extend(audio_chunk)
                            
                            # If buffer is large enough, send
                            if len(self.audio_buffer) >= 4096:
                                # Encode as base64
                                audio_b64 = base64.b64encode(bytes(self.audio_buffer)).decode('ascii')
                                
                                # Send to WebSocket
                                if hasattr(self, 'ws'):
                                    audio_event = {
                                        "type": "input_audio_buffer.append",
                                        "audio": audio_b64
                                    }
                                    self.ws.send(json.dumps(audio_event))
                                    
                                # Clear buffer
                                self.audio_buffer = bytearray()
                
                    # Send any remaining audio
                    if len(self.audio_buffer) > 0:
                        audio_b64 = base64.b64encode(bytes(self.audio_buffer)).decode('ascii')
                        if hasattr(self, 'ws'):
                            audio_event = {
                                "type": "input_audio_buffer.append",
                                "audio": audio_b64
                            }
                            self.ws.send(json.dumps(audio_event))
                    
                    # Let the API know we're done sending audio
                    if hasattr(self, 'ws'):
                        complete_event = {
                            "type": "input_audio_buffer.complete"
                        }
                        self.ws.send(json.dumps(complete_event))
                        
                    print("MIRROR DEBUG: ✅ Done recording - sent complete event")
                    
                    # Clean up
                    self.stop_audio_stream()
                    
                    # Update status
                    self.recording = False
                    self.processing = True
                    self.set_status("Processing", "Processing your request...")
                    
                except Exception as e:
                    self.logger.error(f"Audio stream thread error: {e}")
                    print(f"MIRROR DEBUG: ❌ Audio stream error: {e}")
                    self.recording = False
                    self.set_status("Error", f"Audio stream error: {str(e)[:30]}")
                    
                    # Try to clean up
                    self.stop_audio_stream()
            
            # Start the audio thread
            self.audio_thread = threading.Thread(target=alsa_stream_thread)
            self.audio_thread.daemon = True
            self.audio_thread.start()
            
            self.logger.info("ALSA audio streaming started")
            return True
                
        except Exception as e:
            self.logger.error(f"Error starting audio stream: {e}")
            print(f"MIRROR DEBUG: ❌ Failed to start audio stream: {e}")
            self.set_status("Error", "Failed to start audio")
            self.recording = False
            return False

    def stop_audio_stream(self):
        """Stop audio streaming and release resources"""
        try:
            # Stop recording flag
            self.recording = False
            
            # Terminate arecord process if it exists
            if hasattr(self, 'audio_process') and self.audio_process:
                try:
                    self.audio_process.terminate()
                    self.audio_process.wait(timeout=1)
                    self.audio_process = None
                    self.logger.info("Audio recording process terminated")
                except Exception as e:
                    self.logger.error(f"Error terminating audio process: {e}")
                    
                    # Force kill if needed
                    try:
                        self.audio_process.kill()
                        self.audio_process = None
                    except:
                        pass
            
            # Send any remaining audio in buffer
            if len(self.audio_buffer) > 0:
                audio_b64 = base64.b64encode(bytes(self.audio_buffer)).decode('ascii')
                if hasattr(self, 'ws'):
                    audio_event = {
                        "type": "input_audio_buffer.append",
                        "audio": audio_b64
                    }
                    self.ws.send(json.dumps(audio_event))
            
            # Clear buffer
            self.audio_buffer = bytearray()
            
            self.logger.info("Audio stream stopped")
            print("MIRROR DEBUG: 🎙️ Audio streaming stopped")
        except Exception as e:
            self.logger.error(f"Error stopping audio stream: {e}")
            print(f"MIRROR DEBUG: ❌ Failed to stop audio stream: {e}")

    def play_audio_chunk(self, audio_bytes):
        """Play an audio chunk received from the API"""
        try:
            import tempfile
            import pygame
            
            # Create a temporary file for the audio chunk
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_filename = temp_file.name
                
                # Write WAV header (simplified - adjust if needed)
                temp_file.write(b'RIFF')
                temp_file.write(struct.pack('<I', 36 + len(audio_bytes)))
                temp_file.write(b'WAVE')
                temp_file.write(b'fmt ')
                temp_file.write(struct.pack('<I', 16))  # Subchunk1Size
                temp_file.write(struct.pack('<H', 1))   # PCM format
                temp_file.write(struct.pack('<H', 1))   # Channels
                temp_file.write(struct.pack('<I', 24000))  # Sample rate
                temp_file.write(struct.pack('<I', 24000 * 2))  # ByteRate
                temp_file.write(struct.pack('<H', 2))   # BlockAlign
                temp_file.write(struct.pack('<H', 16))  # BitsPerSample
                temp_file.write(b'data')
                temp_file.write(struct.pack('<I', len(audio_bytes)))
                temp_file.write(audio_bytes)
            
            # Initialize pygame mixer if needed
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000)
            
            # Play the audio
            sound = pygame.mixer.Sound(temp_filename)
            sound.set_volume(self.tts_volume)
            sound.play()
            
            # In a real system, we'd clean up the temp file after playing
            # but for streaming chunks, this might be complex - consider using a queue
            
        except Exception as e:
            self.logger.error(f"Error playing audio chunk: {e}")
