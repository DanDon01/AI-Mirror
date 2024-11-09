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
        self.speaking = False
        self.error_state = False
        
        # Initialize audio processing variables
        self.audio_data = None
        self.current_prompt = None
        self.current_response = None
        self.last_error = None
        
        # Initialize timing variables
        self.button_press_time = 0
        self.last_process_time = 0
        self.min_button_hold_time = 0.1  # seconds
        self.max_recording_time = 30  # seconds
        self.timeout_duration = 10  # seconds
        
        # Initialize display variables
        self.font_size = 36
        self.text_color = (200, 200, 200)
        self.error_color = (255, 0, 0)
        self.success_color = (0, 255, 0)
        
        # Initialize threading components
        self.processing_thread = None
        self.response_queue = Queue()
        self.audio_queue = Queue()
        self.should_stop = False
        
        # Initialize audio settings
        self.audio_volume = config.get('audio', {}).get('wav_volume', 0.7)
        self.tts_volume = config.get('audio', {}).get('tts_volume', 0.7)
        self.mic_energy_threshold = config.get('audio', {}).get('mic_energy_threshold', 1000)
        
        # Initialize pygame mixer for audio if not already initialized
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
        
        # Add a small delay to let the GPIO settle
        time.sleep(0.1)
        
        # Ensure button starts in correct state
        self.button.turn_led_off()
        
        # Initialize error handling
        self.max_retries = 3
        self.retry_count = 0
        self.retry_delay = 1  # seconds
        
        # Initialize conversation history
        self.conversation_history = []
        self.max_history_length = 10
        
        self.logger.info("AI Module initialization complete")

    def update(self):
        try:
            current_button_state = self.button.read()
            
            # Check for button press (transition from HIGH to LOW)
            if current_button_state == 0 and self.last_button_state == 1:
                if not self.recording and not self.processing and not self.listening:
                    self.on_button_press()
            # Check for button release (transition from LOW to HIGH)
            elif current_button_state == 1 and self.last_button_state == 0:
                if self.recording:
                    self.on_button_release()
            
            # Update last button state
            self.last_button_state = current_button_state
            
            # Check for completed responses
            if not self.response_queue.empty():
                response = self.response_queue.get()
                if response:
                    self.speak_response(response)
            
            # Update status message if needed
            current_time = pygame.time.get_ticks()
            if current_time - self.last_status_update > self.status_duration:
                if not self.recording and not self.processing:
                    self.set_status("Idle", "Press button to speak")
                    
        except Exception as e:
            self.logger.error(f"Error in update: {e}")
            self.set_status("Error", "System error occurred")

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
        self.logger.debug("Button press detected")
        if not self.recording and not self.processing:
            self.button.turn_led_on()
            self.button_light_on = True
            self.play_sound_effect('mirror_listening')
            self.recording = True
            self.listening = True
            self.set_status("Listening...", "Speak now")
            self.button_press_time = time.time()

    def on_button_release(self):
        self.logger.debug("Button release detected")
        if self.recording:
            self.recording = False
            self.button.turn_led_off()
            self.button_light_on = False
            if not self.processing:
                self.processing = True
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
