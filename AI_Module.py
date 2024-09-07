import openai
import speech_recognition as sr
from gtts import gTTS
import pygame
import os
import time
from dotenv import load_dotenv
from gpiozero import Button, LED
from gpiozero.pins.pigpio import PiGPIOFactory
import logging
from openai import OpenAI
from config import CONFIG

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 250

class AIInteractionModule:
    def __init__(self, config):
        self.config = config
        self.api_key = config['openai']['api_key']
        self.openai_model = config['openai'].get('model', 'text-davinci-003')
        openai.api_key = self.api_key
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = config.get('audio', {}).get('mic_energy_threshold', 300)
        self.recognizer.dynamic_energy_threshold = False

        self.microphone = sr.Microphone(device_index=2)

        pygame.mixer.init()
        self.listening = False
        self.status = "Idle"
        
        self.sound_effects = {}
        sound_effects_path = CONFIG.get('sound_effects_path', os.path.join('assets', 'sound-effects'))
        for sound_name in ['mirror_listening', 'start_speaking', 'finished_speaking', 'error']:
            try:
                sound_file = os.path.join(sound_effects_path, f"{sound_name}.mp3")
                if os.path.exists(sound_file):
                    self.sound_effects[sound_name] = pygame.mixer.Sound(sound_file)
                else:
                    print(f"Warning: Sound file '{sound_file}' not found. Using silent sound.")
                    self.sound_effects[sound_name] = pygame.mixer.Sound(buffer=b'\x00')
            except pygame.error as e:
                print(f"Error loading sound '{sound_name}': {e}. Using silent sound.")
                self.sound_effects[sound_name] = pygame.mixer.Sound(buffer=b'\x00')

        # Initialize GPIO using gpiozero with PiGPIOFactory
        self.pin_factory = PiGPIOFactory()
        self.button = Button(23, pull_up=False, pin_factory=self.pin_factory)  # GPIO 23 for button, pull-down
        self.led = LED(25, pin_factory=self.pin_factory)  # GPIO 25 for LED

        # Set up button press and release actions
        self.button.when_pressed = self.on_button_press
        self.button.when_released = self.on_button_release

        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)

        self.client = OpenAI(api_key=self.api_key)

    def play_sound_effect(self, sound_name):
        try:
            self.sound_effects[sound_name].set_volume(self.config.get('audio', {}).get('wav_volume', 0.7))
            self.sound_effects[sound_name].play()
        except pygame.error as e:
            self.logger.error(f"Error playing sound effect '{sound_name}': {e}")

    def on_button_press(self):
        self.logger.info("Button press detected")
        print("Button pressed. Listening for speech...")
        self.led.on()
        self.play_sound_effect('mirror_listening')
        self.listening = True
        self.status = "Listening..."

    def on_button_release(self):
        self.logger.info("Button release detected")
        print("Button released.")
        if self.listening:
            self.listen_and_respond()
            self.listening = False
            self.led.off()

    def update(self):
        pass

    def draw(self, screen, position):
        font = pygame.font.Font(None, 36)
        text = font.render(f"AI Status: {self.status}", True, (200, 200, 200))
        screen.blit(text, position)

    def listen_and_respond(self):
        """Listen to the user's question and respond using OpenAI API."""
        self.logger.info("Starting listen_and_respond method")
        with self.microphone as source:
            try:
                self.logger.info("Adjusting for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                self.logger.info("Please say your question...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                self.logger.info("Audio captured successfully")
                
                self.play_sound_effect('start_speaking')
                self.status = "Processing..."
                
                self.logger.info("Recognizing speech...")
                prompt = self.recognizer.recognize_google(audio)
                self.logger.info(f"Speech recognized: {prompt}")
                
                response = self.ask_openai(prompt)
                if response != "Sorry, there was an issue contacting the OpenAI service.":
                    self.logger.info("Speaking response...")
                    self.speak_response(response)
                    self.play_sound_effect('finished_speaking')
                else:
                    self.logger.warning("OpenAI service issue, not speaking response")
                    self.status = "OpenAI service issue"
                    self.play_sound_effect('error')
                    self.speak_response("Sorry, there was an issue contacting the OpenAI service.")
            except sr.WaitTimeoutError:
                self.play_sound_effect('error')
                self.logger.warning("No speech detected within the timeout period")
                self.status = "No speech detected"
                self.speak_response("I didn't hear anything. Could you please try again?")
            except sr.UnknownValueError:
                self.play_sound_effect('error')
                self.logger.warning("Google Speech Recognition could not understand audio")
                self.status = "Speech not understood"
                self.speak_response("I'm sorry, I couldn't understand that. Could you please repeat?")
            except sr.RequestError as e:
                self.play_sound_effect('error')
                self.logger.error(f"Could not request results from Google Speech Recognition service; {e}")
                self.status = "Speech recognition error"
                self.speak_response("There was an issue with the speech recognition service. Please try again later.")
            except Exception as e:
                self.play_sound_effect('error')
                self.logger.error(f"An unexpected error occurred: {e}")
                self.status = "Error occurred"
                self.speak_response("An unexpected error occurred. Please try again.")
            finally:
                self.listening = False
                self.led.off()

    def ask_openai(self, prompt, max_tokens=DEFAULT_MAX_TOKENS):
        """Send the prompt to OpenAI and return the response."""
        formatted_prompt = "You are a magic mirror, someone is looking at you and says this: '{}' reply to this query as an all-knowing benevolent leader, with facts and humor, short but banterful answer, give sass and poke fun at them".format(prompt)
        self.logger.info("Sending formatted prompt to OpenAI: {}".format(formatted_prompt))
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
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
        """Convert text response to speech and play it."""
        self.logger.info(f"Converting text to speech: {text}")
        self.status = "Speaking..."
        try:
            tts = gTTS(text)
            tts.save("response.mp3")
            pygame.mixer.music.load("response.mp3")
            pygame.mixer.music.set_volume(self.config.get('audio', {}).get('tts_volume', 1.0))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            os.remove("response.mp3")
        except Exception as e:
            self.logger.error(f"Error in TTS or playback: {e}")
        finally:
            self.status = "Idle"

    def cleanup(self):
        """This method is called when shutting down the module."""
        pygame.mixer.quit()
        self.led.close()
        self.button.close()
        self.pin_factory.close()
        print("AI Interaction module has been cleaned up.")
