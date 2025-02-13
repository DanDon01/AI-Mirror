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

DEFAULT_MODEL = "gpt-4-1106-preview"
DEFAULT_MAX_TOKENS = 250

class Button:
    def __init__(self, chip_name="/dev/gpiochip0", pin=17):
        self.chip = gpiod.Chip(chip_name)
        self.line = self.chip.get_line(pin)
        self.line.request(consumer="button", type=gpiod.LINE_REQ_DIR_IN)

    def read(self):
        return self.line.get_value()  # 0 is pressed, 1 is not pressed

    def cleanup(self):
        if hasattr(self, 'line'):
            self.line.release()
        if hasattr(self, 'chip'):
            self.chip.close()

class AIInteractionModule:
    def __init__(self, config):
        # Initialize logging
        self.logger = logging.getLogger(__name__)
        self.config = config
        
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
        
        # Initialize speech recognition with configured settings
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = self.mic_energy_threshold
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        self.recognizer.phrase_threshold = 0.5
        self.recognizer.non_speaking_duration = 0.5

        # Initialize microphone with Google Voice HAT
        try:
            # List available microphones
            mics = sr.Microphone.list_microphone_names()
            self.logger.info(f"Available microphones: {mics}")
            
            # Look for Adafruit Voice Bonnet instead of Google Voice HAT
            device_index = None
            for index, name in enumerate(mics):
                # The exact name will depend on how the bonnet identifies itself
                if 'adafruit' in name.lower() or 'voice bonnet' in name.lower():
                    device_index = index
                    self.logger.info(f"Found Adafruit Voice Bonnet at index {index}: {name}")
                    break
            
            if device_index is None:
                self.logger.warning("Voice Bonnet not found by name, using default")
                device_index = None  # Let it use system default
            
            self.microphone = sr.Microphone(
                device_index=device_index,
                sample_rate=48000,
                chunk_size=4096
            )
            
            # Configure recognizer with much higher sensitivity
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = 300    # Lowered to detect quieter sounds
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.dynamic_energy_adjustment_damping = 0.15
            self.recognizer.dynamic_energy_ratio = 1.5
            self.recognizer.pause_threshold = 0.8
            self.recognizer.phrase_threshold = 0.3
            self.recognizer.non_speaking_duration = 0.5
            
            with self.microphone as source:
                self.logger.info("Adjusting for ambient noise...")
                source.gain = 20.0  # Increase microphone gain
                self.recognizer.adjust_for_ambient_noise(source, duration=2)
                self.logger.info(f"Microphone energy threshold set to: {self.recognizer.energy_threshold}")
                
        except Exception as e:
            self.logger.error(f"Error initializing microphone: {str(e)}")
            self.logger.error(traceback.format_exc())

        # Load fallback responses if configured
        self.fallback_config = ai_config.get('fallback_responses', {})
        if self.fallback_config.get('enabled'):
            self.load_fallback_responses()
        
        # Initialize button
        self.button = Button(chip_name="/dev/gpiochip0", pin=17)
        
        # Initialize OpenAI client with credential check
        self.has_openai_access = False
        openai_config = config.get('openai', {})
        if openai_config.get('api_key'):
            try:
                self.client = OpenAI(api_key=openai_config.get('api_key'))
                self.model = openai_config.get('model', DEFAULT_MODEL)
                # Test the connection
                response = self.client.models.list()
                self.has_openai_access = True
                self.logger.info("OpenAI API access confirmed")
            except Exception as e:
                self.logger.warning(f"OpenAI API access failed: {e}")
                self.has_openai_access = False
        
        # Initialize basic text-to-speech as fallback
        self.tts_engine = gTTS
        self.logger.info(f"AI Module initialized with OpenAI access: {self.has_openai_access}")
        
        # Initialize sound effects
        self.sound_effects = {}
        try:
            sound_file = '/home/Dan/Projects/AI-Mirror/assets/sound_effects/mirror_listening.mp3'
            self.logger.info(f"Loading sound file from: {sound_file}")
            if os.path.exists(sound_file):
                self.sound_effects['mirror_listening'] = pygame.mixer.Sound(sound_file)
                self.logger.info("Successfully loaded mirror_listening.mp3")
            else:
                self.logger.error(f"Sound file not found at: {sound_file}")
        except Exception as e:
            self.logger.error(f"Error loading sound: {e}")
        
        # Initialize state variables
        self.status = "Idle"
        self.status_message = "Press button to speak"
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
        
        # These should be the last lines of __init__
        self.set_status("Idle", "Press button to speak")
        self.logger.info("AI Module initialization complete")

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
        # Button is pressed (0) and we're not already processing
        if self.button.read() == 0:
            if not self.recording and not self.processing:
                self.on_button_press()
        else:
            if self.recording:
                self.on_button_release()

    def set_status(self, status, message):
        self.status = status
        self.status_message = message
        self.last_status_update = pygame.time.get_ticks()
        self.logger.debug(f"Status set to: {status} - {message}")

    def play_sound_effect(self, sound_name):
        self.logger.info(f"Attempting to play sound effect: {sound_name}")
        self.logger.info(f"Available sound effects: {list(self.sound_effects.keys())}")
        try:
            if sound_name in self.sound_effects:
                self.logger.info(f"Found sound effect: {sound_name}")
                volume = self.config.get('audio', {}).get('wav_volume', 0.7)
                self.sound_effects[sound_name].set_volume(volume)
                self.sound_effects[sound_name].play()
                self.logger.info(f"Successfully played {sound_name}")
            else:
                self.logger.error(f"Sound effect '{sound_name}' not found in available effects")
        except Exception as e:
            self.logger.error(f"Error playing sound effect '{sound_name}': {str(e)}")

    def on_button_press(self):
        self.logger.info("Processing button press")
        if not self.recording and not self.processing:
            self.button.turn_led_on()
            self.button_light_on = True
            self.play_sound_effect('mirror_listening')
            self.recording = True
            self.listening = True
            self.set_status("Listening...", "Speak now")

    def on_button_release(self):
        self.logger.info("Processing button release")
        if self.recording:
            self.recording = False
            self.button.turn_led_off()
            self.button_light_on = False
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
                self.set_status("Idle", "Press button to speak")

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
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing = False
            self.processing_thread.join(timeout=1.0)
        if hasattr(self, 'button'):
            self.button.cleanup()
