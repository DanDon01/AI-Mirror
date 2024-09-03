import openai
import speech_recognition as sr
from gtts import gTTS
import pygame
import os
import time
from dotenv import load_dotenv

class AIInteractionModule:
    def __init__(self, config):
        self.api_key = config['openai']['api_key']
        self.openai_model = config['openai'].get('model', 'text-davinci-003')
        openai.api_key = self.api_key
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        pygame.mixer.init()
        self.listening = False
        self.status = "Idle"
        
        # Load sound effects
        self.start_sound = pygame.mixer.Sound("start_listening.wav")
        self.end_sound = pygame.mixer.Sound("end_listening.wav")

    def update(self):
        """This method is called by the main loop."""
        if self.listening:
            self.listen_and_respond()
            self.listening = False

    def draw(self, screen, position):
        """This method is called by the main loop to draw any UI elements."""
        font = pygame.font.Font(None, 36)
        text = font.render(f"AI Status: {self.status}", True, (200, 200, 200))
        screen.blit(text, position)

    def handle_event(self, event):
        """Handles Pygame events."""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            self.listening = True
            self.status = "Listening..."
            print("Spacebar pressed. Listening for speech...")
            self.start_sound.play()

    def listen_and_respond(self):
        """Listen to the user's question and respond using OpenAI API."""
        with self.microphone as source:
            print("Adjusting for ambient noise...")
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            print("Please say your question...")
            try:
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                self.end_sound.play()
                self.status = "Processing..."
                
                prompt = self.recognizer.recognize_google(audio)
                print(f"You said: {prompt}")
                response = self.ask_openai(prompt)
                self.speak_response(response)
            except sr.WaitTimeoutError:
                print("No speech detected")
                self.status = "No speech detected"
            except sr.UnknownValueError:
                print("Could not understand audio")
                self.status = "Speech not understood"
            except sr.RequestError as e:
                print(f"Could not request results; {e}")
                self.status = "Speech recognition error"
            except Exception as e:
                print(f"An error occurred: {e}")
                self.status = "Error occurred"

    def ask_openai(self, prompt):
        """Send the prompt to OpenAI and return the response."""
        print("Sending prompt to OpenAI...")
        try:
            response = openai.Completion.create(
                engine=self.openai_model,
                prompt=prompt,
                max_tokens=150,
                temperature=0.7,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0
            )
            answer = response.choices[0].text.strip()
            print(f"OpenAI response: {answer}")
            return answer
        except Exception as e:
            print(f"Error with OpenAI API call: {e}")
            return "Sorry, there was an issue contacting the OpenAI service."

    def speak_response(self, text):
        """Convert text response to speech and play it."""
        self.status = "Speaking..."
        try:
            tts = gTTS(text)
            tts.save("response.mp3")
            pygame.mixer.music.load("response.mp3")
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            os.remove("response.mp3")  # Clean up the audio file after playback
        except Exception as e:
            print(f"Error in TTS or playback: {e}")
        finally:
            self.status = "Idle"

    def cleanup(self):
        """This method is called when shutting down the module."""
        pygame.mixer.quit()
        print("AI Interaction module has been cleaned up.")
