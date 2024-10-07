import asyncio
import websockets
import json
import os
import pygame
import logging
from config import CONFIG

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
        
        pygame.mixer.init()
        self.status = "Idle"
        self.running = True

        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.DEBUG)

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

    async def listen_loop(self):
        """Continuously listens for user interactions and handles responses."""
        try:
            while self.running:
                # Wait for incoming messages from the server
                message = await self.websocket.recv()
                self.handle_message(message)
        except Exception as e:
            self.logger.error(f"Error in listen_loop: {e}")

    async def send_event(self, event):
        """Sends an event to the WebSocket."""
        try:
            await self.websocket.send(json.dumps(event))
            self.logger.info(f"Sent event: {event}")
        except Exception as e:
            self.logger.error(f"Error sending event: {e}")

    async def handle_event(self, event):
        """Handles events such as button press to start interaction."""
        if event.key == pygame.K_SPACE:
            await self.on_button_press()

    async def on_button_press(self):
        """Handles the button press to initiate conversation."""
        self.logger.info("Button press detected")
        self.status = "Listening..."
        await self.send_event({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": "Hello! Start speaking now."  # This would be replaced with speech input in production
                }]
            }
        })

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
        except Exception as e:
            self.logger.error(f"Error processing response: {e}")

    def speak_response(self, text):
        """Plays the response received from the Realtime API."""
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
