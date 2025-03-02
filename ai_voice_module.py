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
            response = self.client.models.list()
            if response:
                model_names = [model.id for model in response]
                print(f"MIRROR DEBUG: Available models: {', '.join(model_names[:5])}...")
                
                # UPDATED: Check for specific models
                self.realtime_model = 'gpt-4o-realtime-preview'
                self.text_model = 'gpt-4o-mini'
                
                # First check for realtime model - this is our primary need
                has_realtime_model = any(self.realtime_model in name for name in model_names)
                if not has_realtime_model:
                    # If not found exactly, look for any realtime model
                    has_any_realtime = any('realtime' in name.lower() for name in model_names)
                    if has_any_realtime:
                        # Find the first realtime model and use it
                        for name in model_names:
                            if 'realtime' in name.lower():
                                self.realtime_model = name
                                has_realtime_model = True
                                print(f"MIRROR DEBUG: Using alternative realtime model: {self.realtime_model}")
                                break
                
                # Check for text model
                has_text_model = any(self.text_model in name for name in model_names)
                if not has_text_model:
                    # Default to any gpt-4 model if mini not available
                    if any('gpt-4' in name for name in model_names):
                        for name in model_names:
                            if 'gpt-4' in name and 'realtime' not in name.lower():
                                self.text_model = name
                                has_text_model = True
                                print(f"MIRROR DEBUG: Using alternative text model: {self.text_model}")
                                break
                
                # Report findings
                if has_realtime_model:
                    self.logger.info(f"OpenAI Realtime API model access confirmed: {self.realtime_model}")
                    print(f"MIRROR DEBUG: ✅ Realtime model available: {self.realtime_model}")
                    self.has_openai_access = True
                    self.set_status("Ready", "Realtime API ready")
                else:
                    self.logger.warning(f"Missing required Realtime model")
                    print(f"MIRROR DEBUG: ⚠️ No realtime model available")
                    self.set_status("Error", "Missing realtime model")
                
                if has_text_model:
                    print(f"MIRROR DEBUG: ✅ Text model available: {self.text_model}")
                else:
                    print(f"MIRROR DEBUG: ⚠️ Preferred text model not available")
            else:
                self.logger.warning("OpenAI Voice API connection test failed")
                print("MIRROR DEBUG: ⚠️ OpenAI Voice API test failed")
                self.set_status("Error", "Voice API connection failed")
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
            import pyaudio
            import numpy as np
            
            self.logger.info("Initializing WebSocket connection to OpenAI Realtime API")
            print("MIRROR DEBUG: 🔄 Starting WebSocket connection to Realtime API")
            
            # Define connection URL with the realtime model
            self.ws_url = f"wss://api.openai.com/v1/realtime?model={self.realtime_model}"
            print(f"MIRROR DEBUG: Using model: {self.realtime_model} for realtime connection")
            
            # Set up headers with API key and beta flag
            self.ws_headers = [
                "Authorization: Bearer " + self.api_key,
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
                        
                        # Configure the session with initial settings and VAD
                        init_event = {
                            "type": "session.update",
                            "session": {
                                "instructions": "You are a helpful assistant running on a Magic Mirror. Be concise but thorough in your responses.",
                                "input_audio_format": {
                                    "type": "audio/wav",
                                    "sampling_rate": 16000,
                                    "encoding": "linear16"
                                },
                                "output_audio_format": {
                                    "type": "audio/wav", 
                                    "sampling_rate": 24000
                                },
                                "turn_detection": {
                                    "mode": "auto",
                                    "speech_activity_timeout": 1.0,
                                    "speech_end_timeout": 0.8
                                }
                            }
                        }
                        ws.send(json.dumps(init_event))
                    
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
                print(f"MIRROR DEBUG: WebSocket connection closed: {close_status_code}")
                self.has_openai_access = False
                self.session_ready = False
                
                # Stop audio stream if active
                self.stop_audio_stream()
            
            # Create WebSocket connection
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                header=self.ws_headers,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Start WebSocket connection in a separate thread
            self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            self.ws_thread.start()
            
            self.logger.info("WebSocket connection thread started")
            
            # Initialize audio streaming
            self.initialize_audio_streaming()
            
        except ImportError as e:
            self.logger.error(f"Missing libraries: {e}")
            print(f"MIRROR DEBUG: ❌ Missing libraries for Realtime API: {e}")
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
        """Set up audio streaming capabilities"""
        try:
            import pyaudio
            import numpy as np
            import struct
            import base64
            
            # Initialize PyAudio for streaming
            self.audio = pyaudio.PyAudio()
            
            # Audio format parameters
            self.format = pyaudio.paInt16
            self.channels = 1
            self.rate = 16000
            self.chunk = 1024
            self.audio_buffer = bytearray()
            
            # VAD settings - can be adjusted
            self.vad_enabled = True
            self.speaking = False
            self.silence_threshold = 500  # Adjust based on environment
            self.silence_counter = 0
            self.max_silence_count = 30  # About 1 second of silence
            
            self.logger.info("Audio streaming initialized")
            print("MIRROR DEBUG: 🎙️ Audio streaming initialized")
            
        except ImportError as e:
            self.logger.error(f"Missing audio libraries: {e}")
            print(f"MIRROR DEBUG: ❌ Cannot initialize audio streaming: {e}")
        except Exception as e:
            self.logger.error(f"Audio streaming initialization error: {e}")
            print(f"MIRROR DEBUG: ❌ Audio streaming error: {e}")

    def start_audio_stream(self):
        """Start streaming audio from microphone to the WebSocket"""
        if not hasattr(self, 'audio') or not self.session_ready:
            self.logger.error("Cannot start audio stream - not initialized")
            return False
        
        try:
            import pyaudio
            import threading
            import base64
            import json
            import struct
            import numpy as np
            
            # Reset audio buffer
            self.audio_buffer = bytearray()
            self.speaking = False
            self.recording = True
            
            # Define callback function for audio stream
            def audio_callback(in_data, frame_count, time_info, status):
                try:
                    if self.recording:
                        # Add incoming audio to buffer
                        self.audio_buffer.extend(in_data)
                        
                        # Check buffer size - send in chunks to avoid overload
                        if len(self.audio_buffer) >= 4096:  # ~256ms of audio at 16kHz
                            # Encode as base64
                            audio_b64 = base64.b64encode(bytes(self.audio_buffer)).decode('ascii')
                            
                            # Send audio chunk to WebSocket
                            if hasattr(self, 'ws'):
                                audio_event = {
                                    "type": "input_audio_buffer.append",
                                    "audio": audio_b64
                                }
                                self.ws.send(json.dumps(audio_event))
                            
                            # Clear buffer after sending
                            self.audio_buffer = bytearray()
                            
                except Exception as e:
                    self.logger.error(f"Audio callback error: {e}")
                
                return (in_data, pyaudio.paContinue)
            
            # Open audio stream
            self.audio_stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk,
                stream_callback=audio_callback
            )
            
            # Start the stream
            self.audio_stream.start_stream()
            self.logger.info("Audio streaming started")
            print("MIRROR DEBUG: 🎙️ Audio streaming started")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting audio stream: {e}")
            print(f"MIRROR DEBUG: ❌ Failed to start audio stream: {e}")
            return False

    def stop_audio_stream(self):
        """Stop audio streaming and release resources"""
        try:
            if hasattr(self, 'audio_stream') and self.audio_stream:
                if self.audio_stream.is_active():
                    self.audio_stream.stop_stream()
                self.audio_stream.close()
                self.audio_stream = None
                
                # Send any remaining audio in buffer
                if len(self.audio_buffer) > 0:
                    audio_b64 = base64.b64encode(bytes(self.audio_buffer)).decode('ascii')
                    if hasattr(self, 'ws'):
                        audio_event = {
                            "type": "input_audio_buffer.append",
                            "audio": audio_b64
                        }
                        self.ws.send(json.dumps(audio_event))
                
                self.audio_buffer = bytearray()
                self.recording = False
                
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
