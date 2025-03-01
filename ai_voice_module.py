import asyncio
import websockets
import json
import os
import pygame
import logging
import threading
import speech_recognition as sr
from gtts import gTTS
from queue import Queue
from config import CONFIG
import time

DEFAULT_MAX_TOKENS = 250

class AIInteractionModule:
    def __init__(self, config):
        self.config = config
        self.api_key = config['openai']['api_key']
        self.ws_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        
        # Initialize pygame mixer if not already initialized
        if not pygame.mixer.get_init():
            pygame.mixer.init()
            
        self.status = "Idle"
        self.status_message = "Say 'Mirror' to activate"
        self.running = True
        self.websocket = None
        self.ws_thread = None
        self.listening_thread = None
        self.hotword_listening = False
        self.conversation_active = False
        
        # Initialize speech recognition
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = config.get('audio', {}).get('mic_energy_threshold', 500)
        self.recognizer.dynamic_energy_threshold = True
        
        # Initialize microphone
        try:
            self.microphone = sr.Microphone()
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
        except Exception as e:
            self.logger.error(f"Error initializing microphone: {e}")
            
        # Response queue for communication with main thread
        self.response_queue = Queue()
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        
        # Start WebSocket connection in a separate thread
        self.ws_thread = threading.Thread(target=self.run_websocket_connection)
        self.ws_thread.daemon = True
        self.ws_thread.start()
        
        # Start hotword detection in a separate thread
        self.listening_thread = threading.Thread(target=self.hotword_detection_loop)
        self.listening_thread.daemon = True
        self.listening_thread.start()

    def run_websocket_connection(self):
        """Runs the WebSocket connection in a separate thread."""
        asyncio.run(self.setup_websocket())

    async def setup_websocket(self):
        """Sets up the WebSocket connection."""
        try:
            async with websockets.connect(self.ws_url, extra_headers=self.headers) as websocket:
                self.websocket = websocket
                self.logger.info("Connected to the Realtime API.")
                await self.listen_loop()
        except Exception as e:
            self.logger.error(f"Error connecting to the Realtime API: {e}")
            self.status = "Error"
            self.status_message = f"Connection error: {str(e)[:50]}"

    async def listen_loop(self):
        """Continuously listens for user interactions and handles responses."""
        try:
            while self.running:
                # Wait for incoming messages from the server
                message = await self.websocket.recv()
                self.handle_message(message)
        except Exception as e:
            self.logger.error(f"Error in listen_loop: {e}")
            self.status = "Error"
            self.status_message = f"Connection error: {str(e)[:50]}"

    def hotword_detection_loop(self):
        """Continuously listens for the hotword 'Mirror'."""
        while self.running:
            if not self.conversation_active:
                try:
                    with self.microphone as source:
                        self.hotword_listening = True
                        self.status = "Listening for hotword"
                        self.status_message = "Say 'Mirror' to activate"
                        
                        audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=3)
                        try:
                            text = self.recognizer.recognize_google(audio).lower()
                            self.logger.debug(f"Heard: {text}")
                            
                            if "mirror" in text:
                                self.logger.info("Hotword detected!")
                                self.status = "Hotword detected"
                                self.status_message = "What can I help you with?"
                                self.conversation_active = True
                                self.activate_conversation()
                        except sr.UnknownValueError:
                            pass  # Speech wasn't understood
                        except sr.RequestError:
                            pass  # Could not request results
                except Exception as e:
                    self.logger.error(f"Error in hotword detection: {e}")
                    time.sleep(1)  # Prevent tight loop on error

    def activate_conversation(self):
        """Activates the conversation after hotword detection."""
        try:
            with self.microphone as source:
                self.status = "Listening..."
                self.status_message = "Listening to your request..."
                
                # Play activation sound if available
                if hasattr(self, 'sound_effects') and 'mirror_listening' in self.sound_effects:
                    self.sound_effects['mirror_listening'].play()
                
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                try:
                    text = self.recognizer.recognize_google(audio)
                    self.logger.info(f"User said: {text}")
                    
                    # Send the text to the WebSocket in a separate thread
                    threading.Thread(target=lambda: 
                        asyncio.run(self.send_user_message(text))
                    ).start()
                    
                except sr.UnknownValueError:
                    self.status = "Error"
                    self.status_message = "Sorry, I didn't catch that"
                    self.conversation_active = False
                except sr.RequestError as e:
                    self.status = "Error"
                    self.status_message = "Speech recognition error"
                    self.conversation_active = False
        except Exception as e:
            self.logger.error(f"Error in activate_conversation: {e}")
            self.conversation_active = False

    async def send_user_message(self, text):
        """Sends a user message to the WebSocket."""
        if self.websocket:
            try:
                await self.websocket.send(json.dumps({
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [{
                            "type": "input_text",
                            "text": text
                        }]
                    }
                }))
                self.logger.info(f"Sent user message: {text}")
            except Exception as e:
                self.logger.error(f"Error sending user message: {e}")
                self.status = "Error"
                self.status_message = "Failed to send message"
                self.conversation_active = False

    def handle_event(self, event):
        """Handles events such as button press to start interaction."""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            if not self.conversation_active:
                self.conversation_active = True
                threading.Thread(target=self.activate_conversation).start()

    def handle_message(self, message):
        """Handles incoming WebSocket messages."""
        try:
            parsed_message = json.loads(message)
            if parsed_message['type'] == 'response.create':
                self.process_response(parsed_message)
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")

    def process_response(self, response):
        """Processes and speaks out the response received from the Realtime API."""
        try:
            text_content = response.get("content", {}).get("text", "")
            if text_content:
                self.speak_response(text_content)
                # Add to response queue for main thread
                self.response_queue.put(('speech', {
                    'user_text': '',  # We don't have the original text here
                    'ai_response': text_content
                }))
        except Exception as e:
            self.logger.error(f"Error processing response: {e}")

    def speak_response(self, text):
        """Plays the response received from the Realtime API."""
        self.logger.info(f"Converting text to speech: {text}")
        self.status = "Speaking..."
        self.status_message = text[:50] + "..." if len(text) > 50 else text
        
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
            self.status_message = "Say 'Mirror' to activate"
            self.conversation_active = False

    def update(self):
        """Called by the main loop to update the module state."""
        # Nothing to do here as the module runs in separate threads
        pass

    def draw(self, screen, position):
        """Draws the module status on the screen."""
        font = pygame.font.Font(None, 36)
        text = font.render(f"AI Status: {self.status}", True, (200, 200, 200))
        screen.blit(text, position)
        if self.status_message:
            message_text = font.render(self.status_message, True, (200, 200, 200))
            screen.blit(message_text, (position[0], position[1] + 40))

    def cleanup(self):
        """Cleans up resources when the module is shutting down."""
        self.running = False
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=1.0)
        if self.listening_thread and self.listening_thread.is_alive():
            self.listening_thread.join(timeout=1.0)
