import openai
import speech_recognition as sr
from gtts import gTTS
import pygame
import os
import logging
import threading
import numpy as np
from openai import OpenAI
from config import CONFIG
import gpiod
from queue import Queue
import asyncio
import time
import traceback
from voice_commands import ModuleCommand

DEFAULT_MODEL = "gpt-4o-mini-2024-07-18"
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
        
        # Initialize speech recognition with adjusted settings
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 1000  # Increased from 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8    # Increased from 0.5
        self.recognizer.phrase_threshold = 0.5   # Increased from 0.3
        self.recognizer.non_speaking_duration = 0.5  # Increased from 0.3
        
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
        
        # Initialize button
        self.button = Button(chip_name="/dev/gpiochip0", pin=17)
        
        # Initialize OpenAI client
        openai_config = config.get('openai', {})
        self.client = OpenAI(api_key=openai_config.get('api_key'))
        self.model = openai_config.get('model', 'gpt-4-mini')
        
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
        
        # Remove any speech logger initialization here as it's now handled by MagicMirror
        
        # Initialize pygame mixer
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        
        # These should be the last lines of __init__
        self.set_status("Idle", "Press button to speak")
        self.logger.info("AI Module initialization complete")

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

    def process_audio_async(self):
        try:
            with self.microphone as source:
                self.logger.info("Listening for speech...")
                self.logger.info(f"Current energy threshold: {self.recognizer.energy_threshold}")
                
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)  # Increased timeouts
                
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
                    # Process as normal AI conversation
                    response = self.ask_openai(text)
                    self.response_queue.put(('speech', {'user_text': text, 'ai_response': response}))

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

    def ask_openai(self, text):
        """Process text through OpenAI API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant for a smart mirror."},
                    {"role": "user", "content": text}
                ],
                max_tokens=DEFAULT_MAX_TOKENS
            )
            return response.choices[0].message.content
        except Exception as e:
            self.logger.error(f"OpenAI API error: {str(e)}")
            return None
