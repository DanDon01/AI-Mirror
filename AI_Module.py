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

DEFAULT_MODEL = "gpt-4o-mini-2024-07-18"
DEFAULT_MAX_TOKENS = 250

class Button:
    def __init__(self, chip_name="/dev/gpiochip0", pin=23):
        self.chip = gpiod.Chip(chip_name)
        self.line = self.chip.get_line(pin)
        self.line.request(consumer="button", type=gpiod.LINE_REQ_DIR_IN)
        self.led_line = None

    def set_led(self, led_pin):
        self.led_line = self.chip.get_line(led_pin)
        self.led_line.request(consumer="led", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[1])

    def read(self):
        return self.line.get_value()

    def turn_led_on(self):
        if self.led_line:
            self.led_line.set_value(0)

    def turn_led_off(self):
        if self.led_line:
            self.led_line.set_value(1)

    def cleanup(self):
        self.line.release()
        if self.led_line:
            self.led_line.release()
        self.chip.close()

class AIInteractionModule:
    def __init__(self, config):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = config.get('audio', {}).get('mic_energy_threshold', 1000)
        self.recognizer.dynamic_energy_threshold = True
        self.microphone = sr.Microphone()
        
        # Initialize button with correct pins
        self.button = Button(chip_name="/dev/gpiochip0", pin=17)
        self.button.set_led(24)
        
        # Initialize OpenAI client
        openai_config = config.get('openai', {})
        self.client = OpenAI(api_key=openai_config.get('api_key'))
        self.model = openai_config.get('model', 'gpt-4-mini')
        
        # Initialize sound effects
        self.sound_effects = {}
        try:
            sound_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                    'assets', 'sound_effects', 'mirror_listening.mp3')
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
        
        # Threading components
        self.processing_thread = None
        self.response_queue = Queue()
        
        # Initialize pygame mixer for audio
        if not pygame.mixer.get_init():
            pygame.mixer.init()

    def update(self):
        if self.button.read() == 0:  # Button is pressed
            if not self.recording and not self.processing and not self.listening:
                self.on_button_press()
        else:  # Button is released
            if self.recording:
                self.on_button_release()

    def set_status(self, status, message):
        self.status = status
        self.status_message = message
        self.last_status_update = pygame.time.get_ticks()
        self.logger.info(f"AI Status: {self.status} - {self.status_message}")

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
        if not self.recording and not self.processing:
            self.logger.info("Button press detected")
            self.button.turn_led_on()
            self.play_sound_effect('mirror_listening')
            self.recording = True
            self.listening = True
            self.set_status("Listening...", "Press button and speak")

    def on_button_release(self):
        if self.recording:
            self.logger.info("Button release detected")
            self.recording = False
            self.button.turn_led_off()
            if not self.processing:
                self.processing = True
                self.processing_thread = threading.Thread(target=self.process_audio_async)
                self.processing_thread.daemon = True
                self.processing_thread.start()

    def process_audio_async(self):
        try:
            with self.microphone as source:
                self.set_status("Processing", "Recognizing speech...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=15)
                
                self.logger.info("Audio captured successfully")
                prompt = self.recognizer.recognize_google(audio)
                self.logger.info(f"Speech recognized: {prompt}")
                
                self.set_status("Processing", f"Recognized: {prompt[:30]}...")
                response = self.ask_openai(prompt)
                
                if response != "Sorry, there was an issue contacting the OpenAI service.":
                    self.set_status("Responding", "AI is speaking")
                    self.response_queue.put(response)
                else:
                    self.set_status("Error", "OpenAI service issue")
                    self.response_queue.put("Sorry, there was an issue contacting the OpenAI service.")
                
        except sr.UnknownValueError:
            self.set_status("Error", "Speech not understood")
            self.response_queue.put("I'm sorry, I couldn't understand that. Could you please repeat?")
        except sr.RequestError as e:
            self.set_status("Error", "Speech recognition service error")
            self.response_queue.put("There was an issue with the speech recognition service. Please try again later.")
        except Exception as e:
            self.logger.error(f"Unexpected error in process_audio_async: {e}")
            self.set_status("Error", "Unexpected error occurred")
            self.response_queue.put("An unexpected error occurred. Please try again.")
        finally:
            self.listening = False
            self.button.turn_led_off()

    def draw(self, screen, position):
        # Only draw if status is not Idle or if status was recently updated
        current_time = pygame.time.get_ticks()
        if (self.status != "Idle" or 
            current_time - self.last_status_update < 1000):
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
