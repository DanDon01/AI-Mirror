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

DEFAULT_MODEL = "gpt-4o-mini-2024-07-18"
DEFAULT_MAX_TOKENS = 250

class Button:
    def __init__(self, chip_name="/dev/gpiochip0", pin=17):
        self.logger = logging.getLogger(__name__)
        self.chip = gpiod.Chip(chip_name)
        self.line = self.chip.get_line(pin)
        self.line.request(consumer="button", type=gpiod.LINE_REQ_DIR_IN)
        self.led_line = None
        self.logger.info(f"Button initialized on pin {pin}")

    def set_led(self, led_pin):
        self.led_line = self.chip.get_line(led_pin)
        self.led_line.request(consumer="led", type=gpiod.LINE_REQ_DIR_OUT)
        self.logger.info(f"LED initialized on pin {led_pin}")

    def read(self):
        value = self.line.get_value()
        self.logger.debug(f"Button read: {value}")
        return value

    def turn_led_on(self):
        if self.led_line:
            self.led_line.set_value(0)
            self.logger.debug("LED turned on")

    def turn_led_off(self):
        if self.led_line:
            self.led_line.set_value(1)
            self.logger.debug("LED turned off")

    def cleanup(self):
        self.line.release()
        if self.led_line:
            self.led_line.release()
        self.chip.close()
        self.logger.info("Button cleaned up")

class AIInteractionModule:
    def __init__(self, config):
        # Initialize logging
        self.logger = logging.getLogger(__name__)
        self.config = config
        
        # Initialize speech recognition
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = config.get('audio', {}).get('mic_energy_threshold', 1000)
        self.recognizer.dynamic_energy_threshold = True
        self.microphone = sr.Microphone()
        
        # Initialize button and LED
        self.button = Button(chip_name="/dev/gpiochip0", pin=17)
        self.button.set_led(24)
        self.button_light_on = False
        self.last_button_state = 1
        
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
        self.button_light_on = False
        self.last_button_state = self.button.read()  # Initialize with actual state
        
        # Threading components
        self.processing_thread = None
        self.response_queue = Queue()
        
        # Initialize pygame mixer
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        
        # These should be the last lines of __init__
        self.set_status("Idle", "Press button to speak")
        self.logger.info("AI Module initialization complete")

    def update(self):
        try:
            current_button_state = self.button.read()
            self.logger.debug(f"Current button state: {current_button_state}, Last button state: {self.last_button_state}")  # Debug logging
            
            # Button is pressed (0)
            if current_button_state == 0 and self.last_button_state == 1:
                self.logger.info("Button press detected")
                if not self.recording and not self.processing and not self.listening:
                    self.on_button_press()
            # Button is released (1)
            elif current_button_state == 1 and self.last_button_state == 0:
                self.logger.info("Button release detected")
                if self.recording:
                    self.on_button_release()
            
            # Update last button state
            self.last_button_state = current_button_state
            
            # Check for completed responses
            if not self.response_queue.empty():
                response = self.response_queue.get()
                if response:
                    self.speak_response(response)
                    
        except Exception as e:
            self.logger.error(f"Error in update: {e}")
            self.logger.error(traceback.format_exc())

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
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self.logger.info("Listening for speech...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                
                self.set_status("Processing", "Recognizing speech...")
                prompt = self.recognizer.recognize_google(audio)
                self.logger.info(f"Recognized: {prompt}")
                
                self.set_status("Processing", "Getting AI response...")
                response = self.ask_openai(prompt)
                
                if response:
                    self.set_status("Responding", "AI is speaking...")
                    self.response_queue.put(response)
                else:
                    self.set_status("Error", "No response from AI")
                    
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
