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
import gpiod
from queue import Queue
import asyncio
import time
import traceback
from voice_commands import ModuleCommand
import json
import websockets  # New import for websocket connections
from typing import Iterator
import subprocess
import pyaudio

DEFAULT_MODEL = "gpt-4-1106-preview"
DEFAULT_MAX_TOKENS = 250

class Button:
    def __init__(self, chip_name="/dev/gpiochip0", pin=17, led_pin=None):
        self.chip = gpiod.Chip(chip_name)
        self.line = self.chip.get_line(pin)
        self.line.request(consumer="button", type=gpiod.LINE_REQ_DIR_IN)
        
        # Setup LED if pin provided
        self.has_led = False
        if led_pin is not None:
            try:
                self.led_line = self.chip.get_line(led_pin)
                self.led_line.request(consumer="led", type=gpiod.LINE_REQ_DIR_OUT)
                self.has_led = True
            except Exception as e:
                print(f"Failed to initialize LED: {e}")

    def read(self):
        return self.line.get_value()  # 0 is pressed, 1 is not pressed
        
    def turn_led_on(self):
        if self.has_led:
            self.led_line.set_value(1)
            
    def turn_led_off(self):
        if self.has_led:
            self.led_line.set_value(0)

    def cleanup(self):
        if hasattr(self, 'led_line') and self.has_led:
            self.led_line.release()
        if hasattr(self, 'line'):
            self.line.release()
        if hasattr(self, 'chip'):
            self.chip.close()

class AIInteractionModule:
    def __init__(self, config):
        # Suppress ALSA errors by setting environment variables
        import os
        # Set environment variables to reduce ALSA verbosity
        os.environ['PYTHONUNBUFFERED'] = '1'  # Ensure output isn't buffered
        
        # Initialize logging first thing
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        )
        self.logger = logging.getLogger("AI_Module")
        self.logger.info("Initializing AI Interaction Module")
        
        self.config = config
        
        # Add flag to track audio availability
        self.has_audio = False
        
        # Allow disabling audio completely via config
        force_no_audio = config.get('force_no_audio', False)
        if force_no_audio:
            self.logger.info("Audio system disabled by configuration")
            self.has_audio = False
            # Skip audio initialization completely
        else:
            # Initialize audio with robust error handling
            self.initialize_audio_system()
        
        # Get configuration from CONFIG object
        ai_config = CONFIG.get('ai_interaction', {}).get('params', {}).get('config', {})
        
        # Initialize OpenAI with credentials check
        self.has_openai_access = False
        self.openai_config = ai_config.get('openai', {})
        if self.openai_config.get('api_key'):
            try:
                self.client = OpenAI(api_key=self.openai_config['api_key'])
                self.model = self.openai_config.get('model', 'gpt-4-1106-preview')
                # Test the connection
                response = self.client.models.list()
                self.has_openai_access = True
                self.logger.info("OpenAI API access confirmed")
            except Exception as e:
                self.logger.warning(f"OpenAI API access failed: {e}")
                self.has_openai_access = False
        
        # Audio configuration from config
        audio_config = ai_config.get('audio', {})
        self.mic_energy_threshold = audio_config.get('mic_energy_threshold', 1000)
        self.tts_volume = audio_config.get('tts_volume', 0.7)
        self.wav_volume = audio_config.get('wav_volume', 0.7)
        
        # Skip the rest of audio initialization if no audio available
        if not self.has_audio:
            self.logger.warning("Audio system unavailable - voice features disabled")
            # Initialize state variables
            self.status = "Limited"
            self.status_message = "Voice features unavailable"
            self.recording = False
            self.processing = False
            self.listening = False
            self.running = True
            return
            
        # Initialize button with fallback
        try:
            self.button = Button(chip_name="/dev/gpiochip0", pin=17)
            self.button_available = True
        except Exception as e:
            self.logger.error(f"Button initialization failed: {e}")
            self.button_available = False
            # Create a dummy button object
            self.button = type('obj', (object,), {
                'read': lambda: 1,
                'turn_led_on': lambda: None,
                'turn_led_off': lambda: None,
                'cleanup': lambda: None
            })
        
        # Initialize sound effects with correct path
        self.sound_effects = {}
        try:
            # Try multiple possible paths
            sound_paths = [
                '/home/dan/Projects/ai_mirror/assets/sound_effects/mirror_listening.mp3',
                '/home/Dan/Projects/AI-Mirror/assets/sound_effects/mirror_listening.mp3',
                '/home/dan/Projects/AI-Mirror/assets/sound_effects/mirror_listening.mp3',
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                             'assets', 'sound_effects', 'mirror_listening.mp3')
            ]
            
            for sound_file in sound_paths:
                self.logger.info(f"Trying sound file at: {sound_file}")
                if os.path.exists(sound_file):
                    self.sound_effects['mirror_listening'] = pygame.mixer.Sound(sound_file)
                    self.logger.info(f"Successfully loaded mirror_listening.mp3 from {sound_file}")
                    break
            else:
                self.logger.error("Sound file not found in any expected location")
                self.create_fallback_sound()  # Create a beep sound instead
        except Exception as e:
            self.logger.error(f"Error loading sound: {e}")
            self.create_fallback_sound()
        
        # Initialize state variables
        self.status = "Idle"
        self.status_message = "Say 'Mirror' or press SPACE to speak"
        self.last_status_update = pygame.time.get_ticks()
        self.status_duration = 5000
        self.recording = False
        self.processing = False
        self.listening = False
        self.last_button_state = self.button.read()
        
        # Threading components
        self.processing_thread = None
        self.response_queue = Queue()
        
        # Initialize command parser
        self.command_parser = ModuleCommand()
              
        # Initialize pygame mixer
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        
        # Add the running attribute
        self.running = True
        
        # These should be the last lines of __init__
        self.set_status("Idle", "Say 'Mirror' or press SPACE to speak")
        self.logger.info("AI Module initialization complete - Listening for 'Mirror' hotword")
        self.logger.info("Available input methods: Hotword 'Mirror' or Space bar keypress")

        # Start hotword detection
        self.hotword_listening = False
        self.listening_thread = threading.Thread(target=self.hotword_detection_loop)
        self.listening_thread.daemon = True
        self.listening_thread.start()

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

    def set_status(self, status, message):
        self.status = status
        self.status_message = message
        self.last_status_update = pygame.time.get_ticks()
        self.logger.debug(f"Status set to: {status} - {message}")

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
        self.logger.info("Starting voice interaction")
        if not self.recording and not self.processing:
            # No need to control physical LED
            self.play_sound_effect('mirror_listening')
            self.recording = True
            self.listening = True
            self.set_status("Listening...", "Speak now")

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

    async def stream_response(self, text: str) -> Iterator[str]:
        """Stream the AI response in real-time"""
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant for a smart mirror."},
                    {"role": "user", "content": text}
                ],
                stream=True  # Enable streaming
            )
            
            self.set_status("Responding", "AI is thinking...")
            response_text = ""
            
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    delta = chunk.choices[0].delta.content
                    response_text += delta
                    # Update the display with the partial response
                    self.status_message = response_text[-50:]  # Show last 50 chars
                    yield delta
            
        except Exception as e:
            self.logger.error(f"Streaming error: {str(e)}")
            yield f"Error: {str(e)}"  # Yield the error instead of returning None

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
            self.button.turn_led_off()
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
        font = pygame.font.Font(None, 36)
        text = font.render(f"AI Status: {self.status}", True, (200, 200, 200))
        screen.blit(text, position)
        if self.status_message:
            message_text = font.render(self.status_message, True, (200, 200, 200))
            screen.blit(message_text, (position[0], position[1] + 40))

    def cleanup(self):
        self.running = False  # Stop the hotword detection loop
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing = False
            self.processing_thread.join(timeout=1.0)
        if hasattr(self, 'button'):
            self.button.cleanup()

    def hotword_detection_loop(self):
        """Continuously listens for the hotword 'Mirror'."""
        # Make sure we have the needed imports
        import time
        
        # Check for FLAC at startup and warn if not available
        try:
            subprocess.check_output(['flac', '--version'])
            flac_available = True
        except (subprocess.SubprocessError, FileNotFoundError):
            self.logger.error("FLAC utility not found - speech recognition will not work properly")
            self.logger.error("Please install FLAC: sudo apt-get install flac")
            flac_available = False
        
        # Skip if audio isn't available
        if not self.has_audio or not flac_available:
            self.logger.warning("Hotword detection disabled - no audio system or missing FLAC")
            return
        
        self.logger.info("🎤 Hotword detection active - listening for 'Mirror'")
        
        while self.running:
            if not self.recording and not self.processing:
                try:
                    with self.microphone as source:
                        self.hotword_listening = True
                        # Use a much more generous timeout
                        audio = self.recognizer.listen(source, 
                                                     timeout=3, 
                                                     phrase_time_limit=5)
                        try:
                            # Use a longer timeout for Google API
                            text = self.recognizer.recognize_google(audio, timeout=5).lower()
                            if "mirror" in text:
                                self.logger.info("🎯 Hotword 'Mirror' detected!")
                                self.on_button_press()
                            else:
                                self.logger.debug(f"Heard: {text} (not hotword)")
                        except sr.UnknownValueError:
                            pass  # Speech wasn't understood
                        except sr.RequestError as e:
                            self.logger.warning(f"Could not request results from Google: {e}")
                            time.sleep(3)  # Wait longer on API errors
                        except OSError as e:
                            if "FLAC conversion utility not available" in str(e):
                                self.logger.error("FLAC utility missing - please install: sudo apt-get install flac")
                                time.sleep(10)  # Wait longer to avoid log spam
                            else:
                                self.logger.error(f"OS Error in speech recognition: {e}")
                                time.sleep(3)
                        
                except Exception as e:
                    self.logger.error(f"Error in hotword detection: {e}")
                    time.sleep(3)  # Wait longer on general errors
                
                # Always sleep a little to prevent tight loops
                time.sleep(0.5)

    def initialize_audio_system(self):
        """Safely initialize the audio system with fallbacks"""
        self.has_audio = False
        
        try:
            # Initialize recognizer first (no device selection yet)
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = 500
            self.recognizer.dynamic_energy_threshold = True
            
            # Get device info without trying to open devices
            p = pyaudio.PyAudio()
            info = p.get_host_api_info_by_index(0)
            numdevices = info.get('deviceCount')
            
            # Find input device
            input_device = None
            for i in range(numdevices):
                try:
                    device_info = p.get_device_info_by_index(i)
                    self.logger.info(f"Device {i}: {device_info['name']}")
                    if device_info.get('maxInputChannels') > 0:
                        input_device = i
                        self.logger.info(f"Using input device: {device_info['name']}")
                        break
                except Exception as e:
                    self.logger.warning(f"Failed to get info for device {i}: {e}")
                
            # Now initialize microphone with explicit device
            if input_device is not None:
                self.microphone = sr.Microphone(device_index=input_device)
                self.has_audio = True
            else:
                self.logger.error("No input devices found")
                self.has_audio = False
            
        except Exception as e:
            self.logger.error(f"Audio initialization error: {e}")
            self.has_audio = False

    def create_fallback_sound(self):
        """Create a simple beep sound as fallback"""
        try:
            import numpy as np
            from scipy.io.wavfile import write
            
            # Generate a simple beep
            sample_rate = 44100
            duration = 1  # seconds
            frequency = 440  # Hz
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            beep = np.sin(2 * np.pi * frequency * t) * 32767
            beep = beep.astype(np.int16)
            
            # Save to temp file
            temp_file = "/tmp/fallback_beep.wav"
            write(temp_file, sample_rate, beep)
            
            # Load into pygame
            self.sound_effects['mirror_listening'] = pygame.mixer.Sound(temp_file)
            self.sound_effects['mirror_listening'].set_volume(1.0)
            self.logger.info("Created fallback beep sound")
            
        except Exception as e:
            self.logger.error(f"Failed to create fallback sound: {e}")

    def handle_event(self, event):
        """Handle keyboard events, specifically the space bar"""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                self.logger.info("Space bar pressed - activating voice input")
                if not self.recording and not self.processing:
                    self.on_button_press()
            elif event.key == pygame.K_RETURN:
                # Using Enter key to simulate button release
                if self.recording:
                    self.on_button_release()
