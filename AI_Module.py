import openai
import speech_recognition as sr
from gtts import gTTS
import pygame
import os
import time
from dotenv import load_dotenv
import gpiod
import logging
import threading
import sounddevice as sd
import numpy as np
from openai import OpenAI
from config import CONFIG

DEFAULT_MODEL = "gpt-4o-mini"
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
        self.config = config
        self.api_key = config['openai']['api_key']
        self.openai_model = config['openai'].get('model', DEFAULT_MODEL)
        openai.api_key = self.api_key
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = config.get('audio', {}).get('mic_energy_threshold', 1000)
        self.recognizer.dynamic_energy_threshold = True
        self.microphone = sr.Microphone()
        pygame.mixer.init()
        self.status = "Idle"
        self.status_message = ""
        self.recording = False
        self.processing = False
        self.button_light_on = False
        self.last_status_update = pygame.time.get_ticks()
        self.status_duration = 5000  # Display status for 5 seconds

        self.sound_effects = {}
        sound_effects_path = CONFIG.get('sound_effects_path', os.path.join('assets', 'sound-effects'))
        for sound_name in ['mirror_listening', 'start_speaking', 'finished_speaking', 'error']:
            try:
                sound_file = os.path.join(sound_effects_path, f"{sound_name}.mp3")
                if os.path.exists(sound_file):
                    self.sound_effects[sound_name] = pygame.mixer.Sound(sound_file)
                else:
                    logging.warning(f"Warning: Sound file '{sound_file}' not found. Using silent sound.")
                    self.sound_effects[sound_name] = pygame.mixer.Sound(buffer=b'\x00')
            except pygame.error as e:
                logging.error(f"Error loading sound '{sound_name}': {e}. Using silent sound.")
                self.sound_effects[sound_name] = pygame.mixer.Sound(buffer=b'\x00')

        self.button = Button(pin=23)
        self.button.set_led(led_pin=25)

        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)

        self.client = OpenAI(api_key=self.api_key)
        self.stream = None
        self.audio_data = []

    def play_sound_effect(self, sound_name):
        try:
            self.sound_effects[sound_name].set_volume(self.config.get('audio', {}).get('wav_volume', 0.7))
            self.sound_effects[sound_name].play()
        except pygame.error as e:
            self.logger.error(f"Error playing sound effect '{sound_name}': {e}")

    def update(self):
        current_time = pygame.time.get_ticks()
        if current_time - self.last_status_update > self.status_duration:
            if not self.recording and not self.processing:
                self.set_status("Idle", "Press button to speak")

        if self.button.read() == 0:  # Button is pressed (active low)
            if not self.recording and not self.processing:
                self.on_button_press()
        else:
            if self.recording:
                self.on_button_release()

        self.update_button_light()

    def on_button_press(self):
        self.logger.info("Button press detected")
        self.recording = True
        self.set_status("Listening", "Release button when done speaking")
        self.play_sound_effect('mirror_listening')
        self.start_recording()

    def on_button_release(self):
        self.logger.info("Button release detected")
        self.recording = False
        self.processing = True
        self.set_status("Processing", "Recognizing speech...")
        self.stop_recording_and_process()

    def set_status(self, status, message):
        self.status = status
        self.status_message = message
        self.last_status_update = pygame.time.get_ticks()
        self.logger.info(f"AI Status: {self.status} - {self.status_message}")

    def draw(self, screen, position):
        font = pygame.font.Font(None, 36)
        text = font.render(f"AI Status: {self.status}", True, (200, 200, 200))
        screen.blit(text, position)
        if self.status_message:
            message_text = font.render(self.status_message, True, (200, 200, 200))
            screen.blit(message_text, (position[0], position[1] + 40))

        # Draw button indicator
        button_color = (0, 255, 0) if self.button_light_on else (255, 0, 0)
        pygame.draw.circle(screen, button_color, (position[0] + 20, position[1] + 100), 10)

    def start_recording(self):
        self.audio_data = []
        
        def audio_callback(indata, frames, time, status):
            if status:
                self.logger.warning(f"Audio callback status: {status}")
            self.audio_data.extend(indata[:, 0])

        self.stream = sd.InputStream(callback=audio_callback, channels=1, samplerate=16000)
        self.stream.start()

    def stop_recording_and_process(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        try:
            audio_np = np.array(self.audio_data)
            audio_amplified = np.int16(audio_np * 32767 * 10)  # Amplify by 10
            
            self.set_status("Processing", "Recognizing speech...")
            prompt = self.recognizer.recognize_google(audio=audio_amplified.tobytes(), 
                                                      language="en-US")
            self.logger.info(f"Speech recognized: {prompt}")
            
            self.set_status("Processing", f"Recognized: {prompt[:30]}...")
            response = self.ask_openai(prompt)
            if response != "Sorry, there was an issue contacting the OpenAI service.":
                self.set_status("Responding", "AI is speaking")
                self.speak_response(response)
            else:
                self.set_status("Error", "OpenAI service issue")
                self.speak_response("Sorry, there was an issue contacting the OpenAI service.")
        except sr.UnknownValueError:
            self.set_status("Error", "Speech not understood")
            self.speak_response("I'm sorry, I couldn't understand that. Could you please repeat?")
        except sr.RequestError as e:
            self.set_status("Error", "Speech recognition service error")
            self.speak_response("There was an issue with the speech recognition service. Please try again later.")
        except Exception as e:
            self.logger.error(f"Unexpected error in stop_recording_and_process: {e}")
            self.set_status("Error", "Unexpected error occurred")
            self.speak_response("An unexpected error occurred. Please try again.")
        finally:
            self.processing = False

    def respond_to_prompt(self, prompt):
        self.set_status("Processing", f"Recognized: {prompt[:30]}...")
        response = self.ask_openai(prompt)
        if response != "Sorry, there was an issue contacting the OpenAI service.":
            self.set_status("Responding", "AI is speaking")
            self.speak_response(response)
        else:
            self.set_status("Error", "OpenAI service issue")
            self.speak_response("Sorry, there was an issue contacting the OpenAI service.")

    def ask_openai(self, prompt, max_tokens=DEFAULT_MAX_TOKENS):
        formatted_prompt = (
            "You are a magic mirror, someone is looking at you and says this: '{}' reply to this query as an "
            "all-knowing benevolent leader, with facts and humor, short but banterful answer, give sass and poke fun at them"
        ).format(prompt)
        self.logger.info("Sending formatted prompt to OpenAI: {}".format(formatted_prompt))
        try:
            response = self.client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": "You are a magic mirror, an all-knowing benevolent leader who responds with short humorous answers."},
                    {"role": "user", "content": formatted_prompt}
                ],
                max_tokens=max_tokens,
                n=1,
                temperature=0.7,
            )
            answer = response.choices[0].message.content.strip()
            self.logger.info("OpenAI response: {}".format(answer))
            return answer
        except Exception as e:
            self.logger.error("Unexpected error with OpenAI API call: {}".format(e))
            return "I'm experiencing some technical difficulties. Please try again later."

    def speak_response(self, text):
        self.logger.info(f"Converting text to speech: {text}")
        try:
            tts = gTTS(text)
            tts.save("response.mp3")
            pygame.mixer.music.load("response.mp3")
            pygame.mixer.music.set_volume(0.7)  # Adjust volume as needed
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            os.remove("response.mp3")
        except Exception as e:
            self.logger.error(f"Error in TTS or playback: {e}")
        finally:
            self.set_status("Idle", "Press button to speak")

    def update_button_light(self):
        if self.recording or self.processing:
            if not self.button_light_on:
                self.button.turn_led_on()
                self.button_light_on = True
        else:
            if self.button_light_on:
                self.button.turn_led_off()
                self.button_light_on = False

    def cleanup(self):
        """This method is called when shutting down the module."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
        self.stream = None
        pygame.mixer.quit()
        self.button.cleanup()
        print("AI Interaction module has been cleaned up.")