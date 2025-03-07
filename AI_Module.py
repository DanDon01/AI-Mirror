import openai
import speech_recognition as sr
from gtts import gTTS
import pygame
import os
import logging
import threading
import numpy as np
from openai import OpenAI, Stream
from config import CONFIG
from queue import Queue
import asyncio
import time
import traceback
from voice_commands import ModuleCommand
import json
import websockets
from typing import Iterator
import subprocess
import pyaudio
import math

DEFAULT_MODEL = "gpt-4o-realtime-preview-2024-12-17"
DEFAULT_MAX_TOKENS = 250

class AIInteractionModule:
    def __init__(self, config_path=None, **kwargs):
        # First thing: set initialization flag
        self._initialized = False
        
        # Initialize logging first thing
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        )
        self.logger = logging.getLogger("AI_Interaction")
        self.logger.info("Initializing AI Interaction Module")
        
        # Load config dynamically to avoid circular import
        if config_path:
            import importlib.util
            spec = importlib.util.spec_from_file_location("config_module", config_path)
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            self.config = config_module.CONFIG
        else:
            self.config = kwargs.get('config', {})
        
        # Initialize required properties with defaults
        self.status = "Initializing"
        self.status_message = "Starting up..."
        self.recording = False
        self.processing = False
        self.has_audio = False
        self.has_openai_access = False
        self.response_queue = Queue()
        self.last_heard_text = ""
        
        # Set up OpenAI configuration
        openai_config = self.config.get('openai', {})
        self.api_key = openai_config.get('api_key')
        
        # Use a model that's definitely available based on the logs
        self.model = openai_config.get('model', 'gpt-4o-realtime-preview-2024-12-17')  # Changed from DEFAULT_MODEL
        self.max_tokens = openai_config.get('max_tokens', DEFAULT_MAX_TOKENS)
        
        # Get audio settings with defaults
        audio_config = self.config.get('audio', {})
        self.mic_energy_threshold = audio_config.get('mic_energy_threshold', 500) 
        self.tts_volume = audio_config.get('tts_volume', 0.8)
        self.wav_volume = audio_config.get('wav_volume', 0.5)
        
        # Check if direct audio mode is enabled (safer approach)
        self.use_direct_audio = kwargs.get('use_direct_audio', False)
        # Still keep the disable flag as fallback
        self.disable_audio = kwargs.get('disable_audio', False)
        
        # Initialize rest of the module
        self.initialize_openai()
        
        # Only initialize audio if not disabled
        if not self.disable_audio:
            self.initialize_audio_system()
            self.load_sound_effects()
        else:
            print("MIRROR DEBUG: 🔇 Audio disabled by configuration")
            self.has_audio = False
            self.status_message = "Ready (audio disabled)"
        
        self.running = True
        
        # Initialize voice command parser
        self.command_parser = ModuleCommand()
        
        # At the end of initialization
        self._initialized = True

    def load_fallback_responses(self):
        """Load fallback responses from configured file"""
        try:
            response_file = self.fallback_config.get('response_file')
            if (response_file and os.path.exists(response_file)):
                with open(response_file, 'r') as f:
                    self.fallback_responses = json.load(f)
                self.logger.info("Loaded fallback responses successfully")
            else:
                self.logger.warning("Fallback responses file not found")
                self.fallback_responses = {}
        except Exception as e:
            self.logger.error(f"Error loading fallback responses: {e}")
            self.fallback_responses = {}

    def update(self):
        # This method is now primarily for hotword processing
        # Physical button is no longer used - interaction is through
        # keyboard space bar or hotword "Mirror"
        pass

    def set_status(self, status, message=None):
        """Set status with logging"""
        self.status = status
        if message:
            self.status_message = message
        self.logger.info(f"Status changed to: {status} - {message}")

    def play_sound_effect(self, sound_name):
        """Play a sound effect with better error handling"""
        self.logger.info(f"Attempting to play sound effect: {sound_name}")
        
        if not self.has_audio:
            self.logger.warning("Cannot play sound effects - audio system unavailable")
            return
        
        try:
            if sound_name in self.sound_effects:
                self.logger.info(f"Found sound effect: {sound_name}")
                
                # Make sure pygame mixer is initialized
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                    
                volume = self.wav_volume  # Use class attribute
                self.sound_effects[sound_name].set_volume(volume)
                
                # Stop any existing sounds to prevent overlap
                pygame.mixer.stop()
                
                # Play the sound
                self.sound_effects[sound_name].play()
                self.logger.info(f"Successfully played {sound_name}")
            else:
                self.logger.error(f"Sound effect '{sound_name}' not found in available effects")
                
        except Exception as e:
            self.logger.error(f"Error playing sound effect '{sound_name}': {str(e)}")
            self.logger.error(traceback.format_exc())

    def on_button_press(self):
        """Handle button press activation"""
        self.logger.info("Activation triggered via button/spacebar")
        print("MIRROR DEBUG: 🔘 Button activation triggered")
        
        # Skip if we're already processing
        if self.recording or self.processing:
            self.logger.info("Already processing, ignoring activation")
            print("MIRROR DEBUG: ⏳ Already processing a request")
            return
        
        # If audio is disabled, use text-only mode
        if self.disable_audio or not self.has_audio:
            print("MIRROR DEBUG: 🔤 Using text-only mode (audio disabled)")
            self.process_text_input("Show me the current weather")
            return
        
        # Rest of the code for audio processing...

    def on_button_release(self):
        self.logger.info("Processing voice input")
        if self.recording:
            self.recording = False
            # No need to control physical LED
            if not self.processing:
                self.processing = True
                self.set_status("Processing", "Processing your speech...")
                self.processing_thread = threading.Thread(target=self.process_audio_async)
                self.processing_thread.daemon = True
                self.processing_thread.start()

    async def stream_response(self, text):
        """Stream response from OpenAI API"""
        try:
            if not self.client:
                self.logger.error("No OpenAI client available")
                yield "I'm sorry, I can't access my AI capabilities right now."
                return
            
            stream = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model,
                messages=[{"role": "user", "content": text}],
                max_tokens=self.max_tokens,
                stream=True
            )
            
            full_response = ""
            async for chunk in stream:
                if not chunk.choices:
                    continue
                
                content = chunk.choices[0].delta.content
                if content:
                    yield content
            
        except Exception as e:
            self.logger.error(f"Error in streaming response: {e}")
            yield f"I'm sorry, I encountered an error: {str(e)[:50]}"

    async def process_with_openai(self, text):
        """Process text using OpenAI's streaming API"""
        try:
            if not self.has_openai_access:
                return self.process_with_fallback(text)

            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant for a smart mirror."},
                    {"role": "user", "content": text}
                ],
                stream=True
            )
            
            full_response = ""
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    delta = chunk.choices[0].delta.content
                    full_response += delta
                    self.status_message = full_response[-50:]
            
            return full_response
            
        except Exception as e:
            self.logger.error(f"OpenAI streaming error: {str(e)}")
            return self.process_with_fallback(text)

    def process_with_fallback(self, text):
        """Process text using basic response templates"""
        responses = {
            "hello": "Hello! How can I help you today?",
            "time": "I can show you the time on the clock module.",
            "weather": "You can check the weather module for current conditions.",
            "help": "I can help you with basic mirror functions and information.",
        }
        
        # Simple keyword matching
        response = "I'm sorry, I can only help with basic functions at the moment."
        for key in responses:
            if key in text.lower():
                response = responses[key]
                break
                
        return response

    async def process_audio_async_helper(self, text):
        """Helper function to process audio asynchronously"""
        try:
            if not self.has_openai_access:
                return self.process_with_fallback(text)

            response = await self.process_with_openai(text)
            return response

        except Exception as e:
            self.logger.error(f"Error in process_audio_async_helper: {str(e)}")
            return self.process_with_fallback(text)

    def process_audio_async(self):
        try:
            with self.microphone as source:
                self.logger.info("Listening for speech...")
                self.logger.info(f"Current energy threshold: {self.recognizer.energy_threshold}")
                
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                
                self.set_status("Processing", "Recognizing speech...")
                text = self.recognizer.recognize_google(audio)
                self.logger.info(f"Recognized: {text}")

                # Check for module commands
                command = self.command_parser.parse_command(text)
                if command:
                    self.logger.debug(f"Executing command: {command}")
                    self.response_queue.put(('command', {'text': text, 'command': command}))
                    self.set_status("Command", f"{command['action']}ing {command['module']}")
                else:
                    # Create event loop and run async processing
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    full_response = loop.run_until_complete(self.process_audio_async_helper(text))
                    loop.close()
                    
                    self.response_queue.put(('speech', {
                        'user_text': text,
                        'ai_response': full_response
                    }))

        except sr.UnknownValueError:
            self.set_status("Error", "Speech not understood")
            self.logger.info("Speech was not understood")
        except sr.RequestError as e:
            self.set_status("Error", "Speech recognition error")
            self.logger.error(f"Could not request results: {e}")
        except Exception as e:
            self.set_status("Error", "An error occurred")
            self.logger.error(f"Error in speech processing: {e}")
        finally:
            self.processing = False
            self.listening = False
            if not self.recording:
                self.set_status("Idle", "Say 'Mirror' or press SPACE to speak")

    def speak_chunk(self, text_chunk):
        """Optional: Implement real-time text-to-speech for response chunks"""
        if len(text_chunk.strip()) > 0:  # Only process non-empty chunks
            try:
                tts = gTTS(text=text_chunk, lang='en', slow=False)
                # Save to temporary file
                temp_file = "temp_chunk.mp3"
                tts.save(temp_file)
                # Play the chunk
                pygame.mixer.music.load(temp_file)
                pygame.mixer.music.play()
                # Clean up
                os.remove(temp_file)
            except Exception as e:
                self.logger.error(f"Error in speak_chunk: {e}")

    def draw(self, screen, position):
        """Enhanced drawing with detailed status indicators"""
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 225)
                height = position.get('height', 200)
            else:
                x, y = position
                width, height = 225, 200
            
            # Draw module background
            pygame.draw.rect(screen, (30, 30, 40), (x, y, width, height))
            pygame.draw.rect(screen, (50, 50, 70), (x, y, width, height), 2)
            
            # Initialize fonts if needed
            if not hasattr(self, 'debug_font'):
                self.debug_font = pygame.font.Font(None, 24)
                self.status_font = pygame.font.Font(None, 36)
            
            # Draw main status
            status_text = self.status_font.render(f"AI: {self.status}", True, (200, 200, 200))
            screen.blit(status_text, (x + 10, y + 10))
            
            # Draw status message
            if self.status_message:
                # Truncate message if too long
                msg = self.status_message
                if len(msg) > 30:
                    msg = msg[:27] + "..."
                
                message_text = self.debug_font.render(msg, True, (200, 200, 200))
                screen.blit(message_text, (x + 10, y + 50))
            
            # Draw connection status indicators
            y_offset = 80
            
            # Mic status
            mic_color = (0, 255, 0) if self.has_audio else (255, 0, 0)
            pygame.draw.circle(screen, mic_color, (x + 20, y + y_offset), 8)
            mic_text = self.debug_font.render("Mic", True, (200, 200, 200))
            screen.blit(mic_text, (x + 35, y + y_offset - 8))
            
            # API status
            api_color = (0, 255, 0) if self.has_openai_access else (255, 0, 0)
            pygame.draw.circle(screen, api_color, (x + 20, y + y_offset + 25), 8)
            api_text = self.debug_font.render("API", True, (200, 200, 200))
            screen.blit(api_text, (x + 35, y + y_offset + 17))
            
            # Recording status
            if self.recording:
                # Pulsing red circle for recording
                pulse = int(128 + 127 * math.sin(pygame.time.get_ticks() / 200))
                rec_color = (255, pulse, pulse)
                pygame.draw.circle(screen, rec_color, (x + 20, y + y_offset + 50), 8)
                rec_text = self.debug_font.render("Recording", True, (255, pulse, pulse))
                screen.blit(rec_text, (x + 35, y + y_offset + 42))
            
            # Processing status
            if self.processing:
                # Pulsing blue circle for processing
                pulse = int(128 + 127 * math.sin(pygame.time.get_ticks() / 300))
                proc_color = (pulse, pulse, 255)
                pygame.draw.circle(screen, proc_color, (x + 20, y + y_offset + 75), 8)
                proc_text = self.debug_font.render("Processing", True, (pulse, pulse, 255))
                screen.blit(proc_text, (x + 35, y + y_offset + 67))
            
            # Display last heard text if available
            if hasattr(self, 'last_heard_text') and self.last_heard_text:
                heard_label = self.debug_font.render("Heard:", True, (180, 180, 220))
                screen.blit(heard_label, (x + 10, y + height - 60))
                
                # Truncate if needed
                heard_text = self.last_heard_text
                if len(heard_text) > 30:
                    heard_text = heard_text[:27] + "..."
                
                text_render = self.debug_font.render(heard_text, True, (220, 220, 255))
                screen.blit(text_render, (x + 10, y + height - 35))
            
        except Exception as e:
            self.logger.error(f"Error in draw: {e}")
            # Simple fallback if drawing fails
            font = pygame.font.Font(None, 28)
            text = font.render(f"AI Module: {self.status}", True, (255, 100, 100))
            screen.blit(text, position)

    def cleanup(self):
        """Safely clean up resources even when audio is disabled"""
        # Stop any running threads
        self.running = False
        
        # Only try to join threads that exist
        if hasattr(self, 'processing_thread') and self.processing_thread and self.processing_thread.is_alive():
            self.processing = False
            self.processing_thread.join(timeout=1.0)
        
        # Only clean up button if it exists and has a cleanup method
        if hasattr(self, 'button') and hasattr(self.button, 'cleanup'):
            self.button.cleanup()

    def initialize_audio_system(self):
        """Initialize audio with direct device approach that avoids enumeration"""
        self.has_audio = False
        
        try:
            import speech_recognition as sr
            import pyaudio
            
            # Create recognizer
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = self.mic_energy_threshold
            self.recognizer.dynamic_energy_threshold = True
            
            print("MIRROR DEBUG: 🎤 Initializing direct audio access")
            
            # Create a safer wrapper for audio input
            class DirectMicrophone(sr.AudioSource):
                def __init__(self, device_index=None, sample_rate=16000, chunk_size=1024):
                    self.device_index = device_index
                    self.SAMPLE_RATE = sample_rate
                    self.CHUNK = chunk_size
                    self.SAMPLE_WIDTH = 2  # 16-bit audio
                    self.CHANNELS = 1  # Mono audio
                    
                    # Required by sr.AudioSource
                    self.stream = None
                    
                def __enter__(self):
                    try:
                        self.audio = pyaudio.PyAudio()
                        
                        # Open stream directly with specific device if provided
                        kwargs = {
                            'format': pyaudio.paInt16,
                            'channels': self.CHANNELS,
                            'rate': self.SAMPLE_RATE,
                            'input': True,
                            'frames_per_buffer': self.CHUNK
                        }
                        
                        # Only add device index if provided
                        if self.device_index is not None:
                            kwargs['input_device_index'] = self.device_index
                            
                        self.stream = self.audio.open(**kwargs)
                        self.stream.start_stream()
                        return self
                    except Exception as e:
                        print(f"MIRROR DEBUG: Error opening audio stream: {e}")
                        if hasattr(self, 'stream') and self.stream:
                            self.stream.close()
                        if hasattr(self, 'audio') and self.audio:
                            self.audio.terminate()
                        raise
                        
                def __exit__(self, exc_type, exc_value, traceback):
                    if hasattr(self, 'stream') and self.stream:
                        self.stream.stop_stream()
                        self.stream.close()
                    if hasattr(self, 'audio') and self.audio:
                        self.audio.terminate()
                    
            # Try to create the microphone with default device first
            try:
                self.microphone = DirectMicrophone()
                self.mic_index = "default"
                self.has_audio = True
                print("MIRROR DEBUG: ✅ Created direct microphone access with default device")
            except Exception as e:
                print(f"MIRROR DEBUG: ❌ Failed with default device: {e}")
                
                # Try with explicit device index as fallback (the USB mic)
                try:
                    self.microphone = DirectMicrophone(device_index=2)  # Try USB mic
                    self.mic_index = 2
                    self.has_audio = True
                    print("MIRROR DEBUG: ✅ Created direct microphone access with device index 2")
                except Exception as e2:
                    print(f"MIRROR DEBUG: ❌ All audio attempts failed: {e2}")
                    self.has_audio = False
        
        except Exception as e:
            print(f"MIRROR DEBUG: ❌ Audio initialization error: {e}")
            self.has_audio = False
        
        # Update status
        if self.has_audio:
            self.status_message = f"Ready with mic {self.mic_index}"
        else:
            self.status_message = "No audio available"

    def create_fallback_sound(self):
        """Create a simple beep sound as fallback"""
        try:
            # Initialize pygame mixer if needed
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=2)
            
            # Create a simple beep using numpy
            sample_rate = 22050
            duration = 0.3  # 300ms beep
            
            # Generate a sine wave
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            beep = np.sin(2 * np.pi * 440 * t) * 0.5  # 440 Hz = A4, 0.5 = 50% volume
            
            # Convert to 16-bit signed integers
            beep = (beep * 32767).astype(np.int16)
            
            # Create a Sound object from the array
            beep_sound = pygame.sndarray.make_sound(np.column_stack([beep, beep]))
            self.sound_effects['mirror_listening'] = beep_sound
            
            self.logger.info("Created fallback beep sound")
        except Exception as e:
            self.logger.error(f"Failed to create fallback sound: {e}")

    def handle_event(self, event):
        """Handle keyboard events, specifically the space bar"""
        try:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    self.logger.info("⌨️ SPACE key pressed - activating voice input")
                    print("MIRROR DEBUG: Space bar pressed - starting listening...")
                    
                    if not self.recording and not self.processing:
                        self.on_button_press()
                    else:
                        print("MIRROR DEBUG: Already recording or processing - ignoring space bar")
                    
                elif event.key == pygame.K_d:
                    # Debug key - show audio device info
                    print("\n=== MIRROR AUDIO DEBUG INFO ===")
                    if hasattr(self, 'mic_index'):
                        print(f"Current microphone index: {self.mic_index}")
                    print(f"Audio available: {self.has_audio}")
                    print(f"OpenAI API available: {self.has_openai_access}")
                    print(f"Current status: {self.status}")
                    
                    # Try to enumerate audio devices
                    try:
                        p = pyaudio.PyAudio()
                        print("\nAVAILABLE AUDIO DEVICES:")
                        for i in range(p.get_device_count()):
                            dev = p.get_device_info_by_index(i)
                            print(f"Device {i}: {dev['name']}")
                            print(f"  Max Input Channels: {dev['maxInputChannels']}")
                            print(f"  Default Sample Rate: {dev['defaultSampleRate']}")
                        p.terminate()
                    except Exception as e:
                        print(f"Could not enumerate audio devices: {e}")
                        
                    print("==============================\n")
                    
                elif event.key == pygame.K_ESCAPE:
                    # Use ESC to cancel recording
                    if self.recording:
                        print("MIRROR DEBUG: Recording canceled by ESC key")
                        self.recording = False
                        self.set_status("Idle", "Recording canceled")
        except Exception as e:
            self.logger.error(f"Error in handle_event: {e}")

    def start_listening(self):
        """Start listening with fixed arguments"""
        try:
            # Configure recognizer with proper timeout handling
            self.recognizer = sr.Recognizer()
            self.recognizer.pause_threshold = 0.8
            self.recognizer.dynamic_energy_threshold = True
            
            # Use a try/except block for each recognition method
            try:
                with sr.Microphone(device_index=self.mic_index) as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    
                    # Use different recognize methods depending on version
                    if hasattr(self.recognizer, 'recognize_sphinx'):
                        # Older version API
                        audio = self.recognizer.listen(source, timeout=10)
                        text = self.recognizer.recognize_sphinx(audio)
                    else:
                        # Newer version API
                        audio = self.recognizer.listen(source)
                        text = self.recognizer.recognize_google(audio)
                    
                    return text.lower()
            except Exception as e:
                logging.error(f"Error in speech recognition: {e}")
                return None
        except Exception as e:
            logging.error(f"Error starting listening: {e}")
            return None

    def process_voice_input(self):
        """Process voice input with enhanced safety"""
        self.logger.info("Starting voice input processing")
        print("MIRROR DEBUG: Attempting to listen for voice input...")
        
        try:
            if not self.has_audio or not hasattr(self, 'microphone'):
                self.logger.error("No audio system available for voice input")
                self.set_status("Error", "No audio system available")
                print("MIRROR DEBUG: ❌ No audio system available")
                self.recording = False
                return
            
            with self.microphone as source:
                # Now try to adjust for ambient noise
                try:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    print("MIRROR DEBUG: Adjusted for ambient noise")
                except Exception as e:
                    print(f"MIRROR DEBUG: ⚠️ Could not adjust for ambient noise: {e}")
                    # Continue anyway
                    
                self.set_status("Listening", "Speak now...")
                print("MIRROR DEBUG: 🎤 Microphone active - speak now")
                
                # Get audio with reasonable timeout
                try:
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                    
                    if audio is None:
                        self.logger.warning("No audio detected")
                        self.set_status("Error", "No speech detected")
                        self.recording = False
                        return
                        
                    self.set_status("Processing", "Converting speech to text...")
                    print("MIRROR DEBUG: 🔍 Processing your speech...")
                    
                    try:
                        # Convert speech to text
                        text = self.recognizer.recognize_google(audio)
                        self.logger.info(f"User said: '{text}'")
                        print(f"MIRROR DEBUG: 👂 Heard: '{text}'")
                        
                        # Store for display
                        self.last_heard_text = text
                        
                        # Process with AI
                        self.set_status("Sending", f"Sending to AI: '{text[:20]}...'")
                        print(f"MIRROR DEBUG: 🔄 Sending to OpenAI: '{text}'")
                        
                        # Start AI processing in a thread
                        threading.Thread(target=self.process_with_ai, args=(text,), daemon=True).start()
                        
                    except sr.UnknownValueError:
                        self.logger.warning("Speech Recognition could not understand audio")
                        self.set_status("Error", "Could not understand speech")
                        print("MIRROR DEBUG: ❌ Could not understand your speech")
                        self.recording = False
                        
                    except sr.RequestError as e:
                        self.logger.error(f"Speech Recognition service error: {e}")
                        self.set_status("Error", "Speech recognition service error")
                        print(f"MIRROR DEBUG: ❌ Speech recognition error: {e}")
                        self.recording = False
                        
                except Exception as e:
                    self.logger.error(f"Error recording audio: {e}")
                    self.set_status("Error", "Error recording audio")
                    print(f"MIRROR DEBUG: ❌ Error recording audio: {e}")
                    self.recording = False
                
        except Exception as e:
            self.logger.error(f"Error in process_voice_input: {e}")
            self.set_status("Error", "Voice processing error")
            print(f"MIRROR DEBUG: ❌ Voice processing error: {e}")
            
        finally:
            # Ensure we always reset recording flag
            self.recording = False

    def process_with_ai(self, text):
        """Process text with AI and handle response"""
        self.processing = True
        
        try:
            self.set_status("Processing", "AI is thinking...")
            print("MIRROR DEBUG: 🧠 OpenAI is processing your request...")
            
            # Check for wake word commands
            if text.lower().startswith(("mirror", "hey mirror", "ok mirror")):
                # Try to extract the actual command
                command_text = text.lower().replace("mirror", "", 1).strip()
                command_text = command_text.replace("hey", "", 1).strip()
                command_text = command_text.replace("ok", "", 1).strip()
                
                # Only use the command part if it exists
                if command_text:
                    text = command_text
                    
            # Log the final text we're sending to the API
            self.logger.info(f"Processing with AI: '{text}'")
            
            # Stream the response from OpenAI
            response_text = ""
            
            # Run the streaming in an async loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def stream_and_collect():
                nonlocal response_text
                async for chunk in self.stream_response(text):
                    response_text += chunk
                    # Update status with last part of response
                    self.set_status("Responding", response_text[-40:])
                    print(f"MIRROR DEBUG: 🗣️ AI: {chunk}", end="", flush=True)
            
            try:
                loop.run_until_complete(stream_and_collect())
                print("\n")  # Add newline after streaming
            finally:
                loop.close()
                
            # Log the response
            self.logger.info(f"AI Response: '{response_text}'")
            print(f"MIRROR DEBUG: ✅ AI response complete: '{response_text[:50]}...'")
            
            # Speak the response
            self.set_status("Speaking", "Speaking response...")
            print("MIRROR DEBUG: 🔊 Converting to speech...")
            self.speak_text(response_text)
            
            # Add to response queue for main thread
            self.response_queue.put(('speech', {
                'user_text': text,
                'ai_response': response_text
            }))
            
            # Check for commands in the response
            self.check_for_commands(text, response_text)
            
        except Exception as e:
            self.logger.error(f"Error in AI processing: {e}")
            self.set_status("Error", f"AI error: {str(e)[:30]}")
            print(f"MIRROR DEBUG: ❌ AI processing error: {e}")
            
        finally:
            self.processing = False
            self.set_status("Idle", "Say 'Mirror' or press SPACE")

    def load_sound_effects(self):
        """Load sound effects for voice interactions (simplified version without hardware)"""
        self.sound_effects = {}
        try:
            # Initialize pygame mixer if not already initialized
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            # Look for sound files in common locations
            sound_paths = CONFIG.get('sound_effects_path', [])
            if not isinstance(sound_paths, list):
                sound_paths = [sound_paths]
            
            # Add default paths as fallbacks
            sound_paths.extend([
                '/home/dan/Projects/ai_mirror/assets/sound_effects',
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'sound_effects')
            ])
            
            # Try to load listening sound
            for base_path in sound_paths:
                if not base_path:
                    continue
                
                listening_file = os.path.join(base_path, 'mirror_listening.mp3')
                if os.path.exists(listening_file):
                    self.logger.info(f"Loading sound effect from: {listening_file}")
                    self.sound_effects['mirror_listening'] = pygame.mixer.Sound(listening_file)
                    break
                
            # If no listening sound was found, create a simple beep
            if 'mirror_listening' not in self.sound_effects:
                self.logger.warning("No listening sound found, creating synthetic sound")
                self.create_fallback_sound()
            
        except Exception as e:
            self.logger.error(f"Error loading sound effects: {e}")
            self.create_fallback_sound()

    def initialize_openai(self):
        """Initialize OpenAI API with support for separate regular and voice keys"""
        self.has_openai_access = False
        self.client = None
        
        try:
            # Get config values
            openai_config = self.config.get('openai', {})
            
            # First try the voice-specific key
            self.api_key = openai_config.get('voice_api_key')
            
            # If not found, try regular api_key from config
            if not self.api_key:
                self.api_key = openai_config.get('api_key')
                if self.api_key:
                    print("MIRROR DEBUG: Using regular API key from config")
            
            # If still no key, try environment variables
            if not self.api_key:
                import os
                # First try voice-specific env var
                self.api_key = os.getenv('OPENAI_VOICE_KEY')
                if self.api_key:
                    print(f"MIRROR DEBUG: Using OPENAI_VOICE_KEY from environment: {self.api_key[:4]}...{self.api_key[-4:] if len(self.api_key) > 8 else ''}")
                else:
                    # Fall back to regular API key
                    self.api_key = os.getenv('OPENAI_API_KEY')
                    if self.api_key:
                        print(f"MIRROR DEBUG: Using fallback OPENAI_API_KEY from environment: {self.api_key[:4]}...{self.api_key[-4:] if len(self.api_key) > 8 else ''}")
            
            if not self.api_key:
                self.logger.error("No OpenAI API key found - checked all possible sources")
                self.set_status("Error", "No API key available")
                print("MIRROR DEBUG: ❌ Could not find any OpenAI API key")
                return
            
            # Create OpenAI client
            openai.api_key = self.api_key
            self.client = OpenAI(api_key=self.api_key)
            
            # Test connection by listing models
            print("MIRROR DEBUG: 🔄 Testing OpenAI API connection...")
            response = self.client.models.list()
            if response:
                self.logger.info("OpenAI API access confirmed")
                model_names = [model.id for model in response]
                print(f"MIRROR DEBUG: Available models include: {model_names[:3]}...")
                
                # Check if we have access to the model we want to use
                if self.model in model_names:
                    print(f"MIRROR DEBUG: ✅ Confirmed access to requested model: {self.model}")
                else:
                    print(f"MIRROR DEBUG: ⚠️ Requested model '{self.model}' not found in available models")
                    
                self.has_openai_access = True
                self.set_status("Ready", "API connection established")
                print("MIRROR DEBUG: ✅ OpenAI API connection successful!")
            else:
                self.logger.warning("OpenAI API connection test returned no models")
                self.set_status("Warning", "API connection issue")
        except Exception as e:
            self.logger.error(f"OpenAI API initialization error: {e}")
            self.set_status("Error", f"API error: {str(e)[:30]}")
            print(f"MIRROR DEBUG: ❌ OpenAI API error: {e}")

    def speak_text(self, text):
        """Convert text to speech and play it"""
        if not text:
            self.logger.warning("Empty text provided for TTS")
            return
        
        try:
            self.logger.info(f"Converting to speech: '{text[:50]}...'")
            
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
            speech.set_volume(self.tts_volume)  # Use the configured volume
            
            # Play the speech
            speech.play()
            
            # Wait for it to finish
            pygame.time.wait(int(speech.get_length() * 1000))
            
            # Clean up
            os.remove(temp_file)
        except Exception as e:
            self.logger.error(f"Error in TTS: {e}")

    def reinitialize_microphone(self):
        """Reinitialize the microphone if it has failed"""
        try:
            # Clear any existing microphone
            self.microphone = None
            
            # Reset the recognizer
            self.recognizer = sr.Recognizer()
            
            # Get the device index from config or use default
            device_idx = self.config.get('audio', {}).get('device_index', None)
            
            # Create a new microphone instance
            print(f"MIRROR DEBUG: Reinitializing microphone with index {device_idx}")
            self.microphone = sr.Microphone(device_index=device_idx)
            
            # Log success
            self.logger.info(f"Microphone reinitialized with index {device_idx}")
            print(f"MIRROR DEBUG: ✅ Microphone reinitialized")
            
            # Ensure we have audio capability
            self.has_audio = True
            
        except Exception as e:
            self.logger.error(f"Failed to reinitialize microphone: {e}")
            print(f"MIRROR DEBUG: ❌ Microphone reinitialization failed: {e}")
            self.has_audio = False
