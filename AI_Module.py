import openai
import speech_recognition as sr
from gtts import gTTS
import pygame
import os
import time
from dotenv import load_dotenv
from gpiozero import Button, LED
import logging
from openai import OpenAI
from config import CONFIG

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 250

class AIInteractionModule:
    def __init__(self, config):
        self.config = config  # Store the entire config
        self.api_key = config['openai']['api_key']
        self.openai_model = config['openai'].get('model', 'text-davinci-003')
        openai.api_key = self.api_key
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = config.get('audio', {}).get('mic_energy_threshold', 300)
        self.recognizer.dynamic_energy_threshold = False

        # Set the correct device index for the VoiceHAT microphone (card 2, device 0)
        self.microphone = sr.Microphone(device_index=2)  # Use device_index=2 for Google VoiceHAT

        # Set up Pygame for sound playback (Google VoiceHAT should be default playback device)
        pygame.mixer.init()
        self.listening = False
        self.status = "Idle"
        
        # Load sound effects
        try:
            self.start_sound = pygame.mixer.Sound("start_listening.wav")
        except pygame.error:
            print("Warning: 'start_listening.wav' not found. Using silent sound.")
            self.start_sound = pygame.mixer.Sound(buffer=b'\x00')  # 1 sample of silence

        try:
            self.end_sound = pygame.mixer.Sound("end_listening.wav")
        except pygame.error:
            print("Warning: 'end_listening.wav' not found. Using silent sound.")
            self.end_sound = pygame.mixer.Sound(buffer=b'\x00')  # 1 sample of silence

        # Set up GPIO for button press and LED control
        self.button = Button(23, pull_up=False)
        self.led = LED(25)

        # Bind button press event to start listening
        self.button.when_pressed = self.on_button_press
        self.button.when_released = self.on_button_release

        print("Button and LED initialized")

        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)

        self.client = OpenAI(api_key=self.api_key)

    def on_button_press(self):
        self.logger.info("Button press detected")
        """Triggered when the button is pressed."""
        print("Button pressed. Listening for speech...")
        self.led.on()
        try:
            self.start_sound.play()
        except pygame.error:
            print("Warning: Could not play start sound.")
        self.listening = True
        self.status = "Listening..."

    def on_button_release(self):
        self.logger.info("Button release detected")
        """Triggered when the button is released."""
        print("Button released.")
        if self.listening:
            self.listen_and_respond()
            self.listening = False
            self.led.off()

    def update(self):
        """This method is called by the main loop."""
        # Remove the listening check from here
        pass

    def draw(self, screen, position):
        """This method is called by the main loop to draw any UI elements."""
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
                self.logger.info("Listening for audio...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                self.logger.info("Audio captured successfully")
                
                try:
                    self.end_sound.play()
                    self.logger.info("End sound played successfully")
                except pygame.error as e:
                    self.logger.error(f"Warning: Could not play end sound. Error: {e}")
                
                self.status = "Processing..."
                
                self.logger.info("Recognizing speech...")
                prompt = self.recognizer.recognize_google(audio)
                self.logger.info(f"Speech recognized: {prompt}")
                
                response = self.ask_openai(prompt)
                if response != "Sorry, there was an issue contacting the OpenAI service.":
                    self.logger.info("Speaking response...")
                    self.speak_response(response)
                else:
                    self.logger.warning("OpenAI service issue, not speaking response")
                    self.status = "OpenAI service issue"
            except sr.WaitTimeoutError:
                self.logger.warning("No speech detected within the timeout period")
                self.status = "No speech detected"
                self.speak_response("I didn't hear anything. Could you please try again?")
            except sr.UnknownValueError:
                self.logger.warning("Google Speech Recognition could not understand audio")
                self.status = "Speech not understood"
                self.speak_response("I'm sorry, I couldn't understand that. Could you please repeat?")
            except sr.RequestError as e:
                self.logger.error(f"Could not request results from Google Speech Recognition service; {e}")
                self.status = "Speech recognition error"
                self.speak_response("There was an issue with the speech recognition service. Please try again later.")
            except Exception as e:
                self.logger.error(f"An unexpected error occurred: {e}")
                self.status = "Error occurred"
                self.speak_response("An unexpected error occurred. Please try again.")
            finally:
                self.listening = False
                self.led.off()

    def ask_openai(self, prompt, max_tokens=DEFAULT_MAX_TOKENS):
        """Send the prompt to OpenAI and return the response."""
        formatted_prompt = f"You are a magic mirror, someone is looking at you and says this: '{prompt}' reply to this query as an all-knowing benevolent leader, with facts and humor"
        self.logger.info(f"Sending formatted prompt to OpenAI: {formatted_prompt}")
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Always use gpt-4o-mini
                messages=[
                    {"role": "system", "content": "You are a magic mirror, an all-knowing benevolent leader who responds with facts and humor."},
                    {"role": "user", "content": formatted_prompt}
                ],
                max_tokens=max_tokens,
                n=1,
                stop=None,
                temperature=0.7,
            )
            answer = response.choices[0].message.content.strip()
            self.logger.info(f"OpenAI response: {answer}")
            return answer
        except openai.error.APIError as e:
            self.logger.error(f"OpenAI API error: {e}")
            return "I'm having trouble connecting to my knowledge base. Please try again in a moment."
        except openai.error.Timeout as e:
            self.logger.error(f"OpenAI API timeout: {e}")
            return "It's taking longer than usual to access my knowledge. Could you please repeat your question?"
        except openai.error.RateLimitError as e:
            self.logger.error(f"OpenAI API rate limit error: {e}")
            return "I'm a bit overwhelmed right now. Can you ask me again in a little while?"
        except Exception as e:
            self.logger.error(f"Unexpected error with OpenAI API call: {e}")
            return "I'm experiencing some technical difficulties. Please try again later."

    def speak_response(self, text):
        """Convert text response to speech and play it."""
        self.logger.info(f"Converting text to speech: {text}")
        self.status = "Speaking..."
        try:
            tts = gTTS(text)
            tts.save("response.mp3")
            self.logger.info("TTS file saved successfully")
            pygame.mixer.music.load("response.mp3")
            pygame.mixer.music.set_volume(self.config.get('audio', {}).get('tts_volume', 1.0))
            pygame.mixer.music.play()
            self.logger.info("Started playing TTS audio")
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            self.logger.info("Finished playing TTS audio")
            os.remove("response.mp3")
            self.logger.info("Removed TTS audio file")
        except Exception as e:
            self.logger.error(f"Error in TTS or playback: {e}")
        finally:
            self.status = "Idle"
            self.logger.info("Speech response completed")

    def cleanup(self):
        """This method is called when shutting down the module."""
        pygame.mixer.quit()
        print("AI Interaction module has been cleaned up.")
