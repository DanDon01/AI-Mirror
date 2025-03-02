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
import random
import pyaudio
import socket  # For DNS testing
import subprocess
import requests

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
        self.initialized = False
        
        # Setup API configuration
        openai_config = self.config.get('openai', {})
        self.api_key = openai_config.get('voice_api_key') or openai_config.get('api_key')
        self.model = openai_config.get('model', 'gpt-4o')
        
        # Audio settings
        audio_config = self.config.get('audio', {})
        self.tts_volume = audio_config.get('tts_volume', 0.8)
        
        # Only perform essential setup in __init__, defer the rest to delayed init
        print("MIRROR DEBUG: 🔄 Setting up basic AI Voice module structure")
        
        # Placeholder for later initialization
        self.session_ready = False
        
        # Defer full initialization
        print("MIRROR DEBUG: 🕒 Deferring full AI Voice module initialization")
        self.set_status("Initializing", "Will initialize after other modules...")
        
        # Start the delayed initialization
        threading.Timer(10.0, self.delayed_initialization).start()
        
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
            
            # Skip WebSocket tests and go straight to fallback method
            print("MIRROR DEBUG: ⚠️ Skipping realtime API - using standard API only")
            self.has_openai_access = True
            self.set_status("Ready", "Using standard API")
            
        except Exception as e:
            self.logger.error(f"OpenAI Voice API initialization error: {e}")
            print(f"MIRROR DEBUG: ❌ Voice API error: {e}")
    
    def start_websocket_connection(self):
        """Start a WebSocket connection to the OpenAI Realtime API using the correct session approach"""
        if not self.api_key:
            self.logger.warning("Cannot start WebSocket - No API key or access")
            print("MIRROR DEBUG: ❌ Cannot start WebSocket - No API key")
            return
        
        try:
            self.logger.info("Initializing WebSocket connection to OpenAI Realtime API")
            print("MIRROR DEBUG: 🔄 Starting Realtime API session using official approach")
            
            import websocket
            import threading
            import requests
            import json
            
            # STEP 1: Create a session via REST API
            print("MIRROR DEBUG: 🔍 Creating Realtime API session...")
            
            session_url = "https://api.openai.com/v1/realtime/sessions"
            session_headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "OpenAI-Beta": "realtime=v1"
            }
            
            session_data = {
                "model": "gpt-4o", 
                "modalities": ["audio", "text"],
                "instructions": "You are a helpful assistant for a smart mirror.",
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16"
            }
            
            try:
                session_response = requests.post(
                    session_url, 
                    headers=session_headers,
                    json=session_data
                )
                
                if session_response.status_code != 200:
                    print(f"MIRROR DEBUG: ❌ Failed to create Realtime session: {session_response.status_code}")
                    print(f"MIRROR DEBUG: Response: {session_response.text}")
                    return False
                
                # Parse the session response
                session_info = session_response.json()
                print("MIRROR DEBUG: ✅ Realtime session created successfully")
                
                # Get the ephemeral token from client_secret
                client_secret = session_info.get("client_secret", {}).get("value")
                if not client_secret:
                    print("MIRROR DEBUG: ❌ No client_secret in session response")
                    return False
                    
                print(f"MIRROR DEBUG: ✅ Got ephemeral token: {client_secret[:4]}...")
                
                # STEP 2: Use the ephemeral token to connect to WebSocket
                self.ws_url = "wss://realtime.api.openai.com/v1/chat/completions"
                
                # Use the client_secret as the authorization token
                self.ws_headers = [
                    f"Authorization: Bearer {client_secret}",
                    "Content-Type: application/json"
                ]
                
            except Exception as e:
                print(f"MIRROR DEBUG: ❌ Error creating Realtime session: {e}")
                return False
            
            # Define event handlers for WebSocket
            def on_message(ws, message):
                try:
                    # Parse the message as JSON
                    data = json.loads(message)
                    
                    print(f"MIRROR DEBUG: 📄 WebSocket message received: {message[:100]}...")
                    
                    # Handle streaming response chunks
                    if "choices" in data:
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            print(f"MIRROR DEBUG: 💬 Received text: {content}")
                    
                    # Handle audio chunks
                    if "audio" in data:
                        audio_data = base64.b64decode(data["audio"])
                        print(f"MIRROR DEBUG: 🔊 Received audio chunk: {len(audio_data)} bytes")
                        # Play the audio chunk
                        self.play_audio_chunk(audio_data)
                    
                except Exception as e:
                    print(f"MIRROR DEBUG: ❌ Error processing WebSocket message: {e}")
            
            def on_error(ws, error):
                import traceback
                self.logger.error(f"WebSocket error: {error}\n{traceback.format_exc()}")
                print(f"MIRROR DEBUG: ❌ WebSocket error: {error}")
                print(f"MIRROR DEBUG: 🔍 Will attempt to reconnect automatically")
            
            def on_close(ws, close_status_code, close_msg):
                self.logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
                print(f"MIRROR DEBUG: ❌ WebSocket closed - Attempting reconnect...")
                
                # Mark session as not ready
                self.session_ready = False

                # Restart session fully
                if self.running:
                    print("MIRROR DEBUG: 🔄 Restarting WebSocket session in 5 seconds...")
                    time.sleep(5)
                    self.reset_websocket_session()
            
            def on_open(ws):
                self.logger.info("WebSocket connection opened")
                print("MIRROR DEBUG: ✅ WebSocket connection established")
                
                # Mark session as ready
                self.session_ready = True
            
            # Create a new WebSocket connection
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                header=self.ws_headers,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Run the WebSocket connection in a separate thread
            self.ws_thread = threading.Thread(target=self.ws.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            
            self.logger.info("WebSocket connection thread started")
            
        except Exception as e:
            self.logger.error(f"Error starting WebSocket: {e}")
            print(f"MIRROR DEBUG: ❌ Error starting WebSocket: {e}")
    
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
        """Handle button press to start voice recording"""
        try:
            # If currently processing, stop it
            if self.recording or self.processing:
                self.stop_audio_stream()
                return
            
            # Check if initialization is complete
            if not self.initialized:
                print("MIRROR DEBUG: ⏳ Module still initializing, please wait...")
                self.set_status("Initializing", "Please wait...")
                return
            
            # Check WebSocket status and decide which method to use
            if hasattr(self, 'ws') and self.session_ready:
                print("MIRROR DEBUG: 🎙️ Using WebSocket for voice interaction")
                self.start_audio_stream()
            else:
                # Use fallback API approach
                print("MIRROR DEBUG: 🎙️ Using standard API for voice interaction")
                self.fallback_voice_api()
        
        except Exception as e:
            print(f"MIRROR DEBUG: ❌ Button press error: {e}")
            self.set_status("Error", "Button press error")
    
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
        """Stream audio to the Realtime API using the correct format"""
        if not hasattr(self, 'session_ready') or not self.session_ready:
            self.logger.error("Cannot start audio stream - WebSocket session not ready")
            return False
        
        try:
            import threading
            import subprocess
            import base64
            import time
            
            # Reset session state
            self.recording = True
            self.processing = False
            
            print("MIRROR DEBUG: 🎙️ Starting audio capture for Realtime API")
            self.set_status("Listening", "Listening...")
            
            # Define the streaming function
            def record_and_stream():
                try:
                    # Create a unique filename for this recording
                    temp_wav = os.path.join(os.getcwd(), f"recording_{int(time.time())}.wav")
                    
                    # Use simple recording command
                    cmd = ["arecord", "-d", "5", "-f", "S16_LE", "-r", "24000", temp_wav]
                    print(f"MIRROR DEBUG: 🎙️ Running: {' '.join(cmd)}")
                    
                    # Run the command
                    process = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if process.returncode == 0 and os.path.exists(temp_wav):
                        file_size = os.path.getsize(temp_wav)
                        print(f"MIRROR DEBUG: ✅ Recording successful: {temp_wav} ({file_size} bytes)")
                        
                        # Only proceed if we got actual audio
                        if file_size > 100:  # More than just the WAV header
                            # Read the WAV file
                            with open(temp_wav, 'rb') as f:
                                # Skip WAV header (44 bytes)
                                f.seek(44)
                                audio_data = f.read()
                            
                            # Clean up
                            try:
                                os.remove(temp_wav)
                            except:
                                pass
                            
                            # Send to Realtime API using the correct format
                            if hasattr(self, 'ws') and len(audio_data) > 1600:
                                # Base64 encode the audio
                                encoded_audio = base64.b64encode(audio_data).decode('utf-8')
                                
                                # Realtime API message format
                                message = {
                                    "audio": encoded_audio,
                                    "content_type": "audio/pcm16;rate=24000"
                                }
                                
                                # Send the message
                                print(f"MIRROR DEBUG: 📤 Sending {len(audio_data)} bytes of audio")
                                self.ws.send(json.dumps(message))
                                
                                # Update status
                                self.recording = False
                                self.processing = True
                                self.set_status("Processing", "Processing your request...")
                            else:
                                print("MIRROR DEBUG: ⚠️ WebSocket not ready or audio too short")
                                self.recording = False
                                self.set_status("Error", "Connection issue")
                        else:
                            print("MIRROR DEBUG: ⚠️ Not enough audio recorded")
                            self.recording = False
                            self.set_status("Error", "No audio captured")
                    else:
                        print(f"MIRROR DEBUG: ❌ Recording failed: {process.stderr}")
                        self.recording = False
                        self.set_status("Error", "Recording failed")
                
                except Exception as e:
                    import traceback
                    print(f"MIRROR DEBUG: ❌ Error: {e}")
                    print(traceback.format_exc())
                    self.recording = False
                    self.set_status("Error", "Recording error")
            
            # Start the recording thread
            self.audio_thread = threading.Thread(target=record_and_stream)
            self.audio_thread.daemon = True
            self.audio_thread.start()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting audio: {e}")
            print(f"MIRROR DEBUG: ❌ Error: {e}")
            self.recording = False
            return False

    def stop_audio_stream(self):
        """Stop the audio streaming process"""
        try:
            # Mark that we're stopping recording
            self.logger.info("Stopping audio streaming")
            print("MIRROR DEBUG: 🛑 Stopping audio streaming")
            
            # Set flag to indicate we're stopping deliberately
            self.stopping_deliberately = True
            
            # Set recording to false to stop the streaming thread
            self.recording = False
            
            # Terminate the arecord process if it exists
            if hasattr(self, 'arecord_process') and self.arecord_process:
                try:
                    self.arecord_process.terminate()
                    self.arecord_process.wait(timeout=1)
                    print("MIRROR DEBUG: 🎙️ arecord process terminated")
                except:
                    # Force kill if needed
                    try:
                        self.arecord_process.kill()
                        print("MIRROR DEBUG: 🎙️ arecord process killed")
                    except:
                        pass
            
            # Update status
            self.processing = True
            self.set_status("Processing", "Processing your request...")
            
        except Exception as e:
            self.logger.error(f"Error stopping audio stream: {e}")
            print(f"MIRROR DEBUG: ❌ Error stopping audio stream: {e}")

    def play_audio_chunk(self, audio_bytes):
        """Play an audio chunk received from the API"""
        try:
            import tempfile
            import os
            import subprocess
            import shutil
            
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
                temp_file.write(struct.pack('<I', 24000 * 2))  # Byte rate
                temp_file.write(struct.pack('<H', 2))   # Block align
                temp_file.write(struct.pack('<H', 16))  # Bits per sample
                
                # Data chunk
                temp_file.write(b'data')
                temp_file.write(struct.pack('<I', len(audio_bytes)))
                temp_file.write(audio_bytes)
            
            # Try multiple playback methods in order of preference
            played = False
            
            # 1. Try aplay first (most reliable on Linux)
            if shutil.which("aplay"):
                try:
                    print("MIRROR DEBUG: 🔊 Playing audio with aplay")
                    subprocess.run(["aplay", temp_filename], 
                                   stderr=subprocess.DEVNULL, 
                                   stdout=subprocess.DEVNULL)
                    played = True
                except Exception as e:
                    print(f"MIRROR DEBUG: ⚠️ aplay failed: {e}")
            
            # 2. Try paplay (PulseAudio) as fallback
            if not played and shutil.which("paplay"):
                try:
                    print("MIRROR DEBUG: 🔊 Playing audio with paplay")
                    subprocess.run(["paplay", temp_filename],
                                   stderr=subprocess.DEVNULL, 
                                   stdout=subprocess.DEVNULL)
                    played = True
                except Exception as e:
                    print(f"MIRROR DEBUG: ⚠️ paplay failed: {e}")
            
            # 3. Try pygame as last resort
            if not played:
                try:
                    print("MIRROR DEBUG: 🔊 Playing audio with pygame")
                    pygame.mixer.init(frequency=24000)
                    sound = pygame.mixer.Sound(temp_filename)
                    sound.play()
                    played = True
                except Exception as e:
                    print(f"MIRROR DEBUG: ⚠️ pygame playback failed: {e}")
            
            # Auto-clean up the temporary file after a delay
            def cleanup_audio_file():
                time.sleep(3)  # Wait for playback to finish
                try:
                    os.remove(temp_filename)
                    print(f"MIRROR DEBUG: 🧹 Cleaned up audio file")
                except:
                    pass
            
            # Start cleanup thread
            cleanup_thread = threading.Thread(target=cleanup_audio_file)
            cleanup_thread.daemon = True
            cleanup_thread.start()
            
            if not played:
                print("MIRROR DEBUG: ❌ Failed to play audio through any method")
            
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

    def reset_and_create_new_session(self):
        """Create a fresh session for every interaction"""
        try:
            print("\nMIRROR DEBUG: 🔄 Creating new Realtime API session")
            
            # Close existing WebSocket if any
            if hasattr(self, 'ws') and self.ws:
                try:
                    self.ws.close()
                    print("MIRROR DEBUG: 🔄 Closed existing WebSocket")
                except:
                    pass
            
            # Reset all state variables
            self.session_ready = False
            self.recording = False
            self.processing = False
            if hasattr(self, 'response_complete'):
                delattr(self, 'response_complete')
            if hasattr(self, 'speech_started'):
                delattr(self, 'speech_started')
            if hasattr(self, 'response_started'):
                delattr(self, 'response_started')
            
            # Start new WebSocket
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
                print("MIRROR DEBUG: ⚠️ Failed to create new session")
                return False
            
        except Exception as e:
            print(f"MIRROR DEBUG: ❌ Error creating new session: {e}")
            return False

    def reset_and_test_api(self):
        """Completely reset and test the API connection"""
        try:
            print("\nMIRROR DEBUG: 🔄 Running full API diagnostic test")
            
            # 1. Check API key
            if not self.api_key:
                print("MIRROR DEBUG: ❌ No API key available")
                return False
            
            print(f"MIRROR DEBUG: ✓ API key available (starts with {self.api_key[:4]}...)")
            
            # 2. Make a very simple API call to test basic connectivity
            import requests
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            # Try the models endpoint - should work for any valid key
            response = requests.get('https://api.openai.com/v1/models', headers=headers)
            if response.status_code != 200:
                print(f"MIRROR DEBUG: ❌ Basic API test failed: {response.status_code} - {response.text}")
                return False
            
            print("MIRROR DEBUG: ✓ Basic API connection successful")
            
            # 3. Test realtime API access specifically
            headers['OpenAI-Beta'] = 'realtime=v1'
            response = requests.get(f'https://api.openai.com/v1/models/{self.realtime_model}', headers=headers)
            
            if response.status_code != 200:
                print(f"MIRROR DEBUG: ❌ Realtime API access test failed: {response.status_code}")
                print(f"MIRROR DEBUG: Response: {response.text}")
                print("MIRROR DEBUG: Your account may not have access to the Realtime API")
                return False
            
            print(f"MIRROR DEBUG: ✓ Confirmed access to Realtime API model: {self.realtime_model}")
            
            # 4. Try a very simple text-only request through the API
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.api_key)
                
                completion = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "Say hello in one word"}],
                    max_tokens=10
                )
                
                print(f"MIRROR DEBUG: ✓ Simple API request successful: {completion.choices[0].message.content}")
            except Exception as api_err:
                print(f"MIRROR DEBUG: ❌ Simple API request failed: {api_err}")
            
            return True
            
        except Exception as e:
            print(f"MIRROR DEBUG: ❌ API diagnostic failed: {e}")
            return False

    def fallback_voice_api(self):
        """Use regular API for voice interaction"""
        print("MIRROR DEBUG: 🎙️ Starting voice interaction with standard API")
        
        try:
            self.set_status("Listening", "Recording audio...")
            
            # Create a unique filename for this recording
            temp_wav = os.path.join(os.getcwd(), f"recording_{int(time.time())}.wav")
            
            # Use the default audio device - no hardware ID
            cmd = ["arecord", "-d", "5", "-f", "S16_LE", "-r", "16000", temp_wav]
            print(f"MIRROR DEBUG: 🎙️ Running: {' '.join(cmd)}")
            
            # Run the command and capture any errors
            process = subprocess.run(cmd, capture_output=True, text=True)
            
            if process.returncode != 0:
                print(f"MIRROR DEBUG: ❌ Recording failed: {process.stderr}")
                self.set_status("Error", "Recording failed")
                return False
            
            # Check if file was created and has content
            if os.path.exists(temp_wav) and os.path.getsize(temp_wav) > 100:
                print(f"MIRROR DEBUG: ✅ Recorded {os.path.getsize(temp_wav)} bytes of audio")
                
                # Transcribe the audio
                self.set_status("Processing", "Transcribing audio...")
                with open(temp_wav, "rb") as audio_file:
                    transcription = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                
                print(f"MIRROR DEBUG: 📝 Transcribed: {transcription.text}")
                
                # Generate response
                self.set_status("Processing", "Generating response...")
                completion = self.client.chat.completions.create(
                    model="gpt-4o-mini",  # Use a more widely available model
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant for a smart mirror."},
                        {"role": "user", "content": transcription.text}
                    ]
                )
                
                response_text = completion.choices[0].message.content
                print(f"MIRROR DEBUG: 💬 Response: {response_text}")
                
                # Generate speech
                self.set_status("Speaking", "Playing response...")
                speech_file = os.path.join(os.getcwd(), "response.mp3")
                response = self.client.audio.speech.create(
                    model="tts-1",
                    voice="alloy",
                    input=response_text
                )
                response.stream_to_file(speech_file)
                
                # Play the audio with multiple fallbacks
                try:
                    # First try mpg123
                    subprocess.run(["mpg123", speech_file], check=False)
                except:
                    try:
                        # Then try pygame
                        import pygame
                        pygame.mixer.init()
                        pygame.mixer.music.load(speech_file)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            pygame.time.Clock().tick(10)
                    except Exception as e:
                        print(f"MIRROR DEBUG: ❌ Could not play audio: {e}")
                
                # Clean up
                try:
                    os.remove(temp_wav)
                    os.remove(speech_file)
                except:
                    pass
                
                self.set_status("Ready", "API ready")
                return True
            else:
                print("MIRROR DEBUG: ❌ No audio recorded or file too small")
                self.set_status("Error", "No audio recorded")
                return False
            
        except Exception as e:
            print(f"MIRROR DEBUG: ❌ Voice API error: {e}")
            self.set_status("Error", "API error")
            return False

    def delayed_initialization(self):
        """Delayed initialization to allow other modules to connect first"""
        try:
            print("MIRROR DEBUG: 🔄 Starting delayed AI Voice module initialization")
            
            # Basic checks for audio hardware
            print("MIRROR DEBUG: 🔍 Checking audio device usage:")
            try:
                result = subprocess.run(["fuser", "-v", "/dev/snd/*"], capture_output=True, text=True)
                print(result.stdout)
                print(result.stderr)
            except Exception as e:
                print(f"MIRROR DEBUG: Could not check audio device usage: {e}")
            
            # Initialize OpenAI
            self.initialize_openai()
            
            # Load sound effects
            self.load_sound_effects()
            
            # Try WebSocket connection with retries
            self.retry_websocket_connection()
            
            # Mark as initialized
            self.initialized = True
            print("MIRROR DEBUG: ✅ AI Voice module initialization complete")
            
        except Exception as e:
            import traceback
            self.logger.error(f"Error in delayed initialization: {e}")
            print(f"MIRROR DEBUG: ❌ Delayed initialization error: {e}")
            print(traceback.format_exc())
            # Still mark as initialized so we can use fallback
            self.initialized = True
            self.set_status("Ready", "Using fallback API")

    def retry_websocket_connection(self):
        """Attempt to establish WebSocket connection with retry pattern"""
        try:
            if not self.api_key:
                print("MIRROR DEBUG: ❌ No API key for WebSocket connection")
                return
            
            # Try to establish connection with decreasing frequency
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                print(f"MIRROR DEBUG: 🔄 WebSocket connection attempt {attempt}/{max_retries}")
                
                # Try to establish connection
                try:
                    if self.start_websocket_connection():
                        print("MIRROR DEBUG: ✅ WebSocket connection successful")
                        return True
                except Exception as e:
                    print(f"MIRROR DEBUG: ❌ WebSocket attempt {attempt} failed: {e}")
                
                # Wait before next retry with increasing delay
                retry_delay = 5 * attempt  # 5s, 10s, 15s
                print(f"MIRROR DEBUG: 🕒 Waiting {retry_delay}s before next attempt...")
                time.sleep(retry_delay)
            
            # If we get here, all retries failed
            print("MIRROR DEBUG: ⚠️ All WebSocket connection attempts failed")
            print("MIRROR DEBUG: 🔄 Will use fallback API approach")
            return False
            
        except Exception as e:
            print(f"MIRROR DEBUG: ❌ Retry process failed: {e}")
            return False
