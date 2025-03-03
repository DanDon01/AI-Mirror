import asyncio
import websockets
import json
import os
import pygame
import logging
import threading
import base64
import time
import requests
from queue import Queue
from config import CONFIG
import subprocess
import pyaudio

class AIVoiceModule:
    def __init__(self, config):
        self.logger = logging.getLogger("AI_Voice")
        self.logger.info("Initializing AI Voice Module")
        
        self.config = config or {}
        self.status = "Initializing"
        self.status_message = "Starting voice systems..."
        self.recording = False
        self.processing = False
        self.session_ready = False
        self.running = True
        self.response_queue = Queue()
        
        # Audio configuration
        self.audio_config = self.config.get('audio', {})
        self.sample_rate = 24000  # Required by OpenAI Realtime API
        self.channels = 1
        self.format = pyaudio.paInt16
        
        # API configuration
        self.api_key = self.config.get('openai', {}).get('api_key')
        self.ws_url = "wss://api.openai.com/v1/realtime"
        
        # Initialize audio
        self.pyaudio = pyaudio.PyAudio()
        
        # Start initialization in a separate thread
        threading.Thread(target=self.initialize, daemon=True).start()

    def initialize(self):
        """Initialize the module and establish WebSocket connection"""
        try:
            if not self.api_key:
                self.logger.error("No OpenAI API key provided")
                self.set_status("Error", "No API key")
                return
                
            self.setup_audio()
            self.connect_websocket()
            self.set_status("Ready", "Press SPACE to speak")
            
        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            self.set_status("Error", f"Init failed: {str(e)}")

    def setup_audio(self):
        """Setup audio input/output"""
        try:
            # Find USB microphone (device index 2 in your case)
            self.input_device_index = 2
            self.stream = self.pyaudio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.input_device_index,
                frames_per_buffer=1024
            )
            self.logger.info("Audio setup complete")
        except Exception as e:
            self.logger.error(f"Audio setup failed: {e}")
            self.set_status("Error", "Audio setup failed")

    async def websocket_handler(self):
        """Handle WebSocket connection and messages"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        
        try:
            async with websockets.connect(
                self.ws_url,
                extra_headers=headers
            ) as websocket:
                self.websocket = websocket
                self.session_ready = True
                self.logger.info("WebSocket connected")
                
                # Send initial configuration
                await websocket.send(json.dumps({
                    "type": "session.update",
                    "session": {
                        "model": "gpt-4o",
                        "modalities": ["text", "audio"],
                        "instructions": "You are a helpful assistant for a smart mirror.",
                        "voice": "alloy",
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16"
                    }
                }))
                
                # Handle incoming messages
                async for message in websocket:
                    data = json.loads(message)
                    event_type = data.get("type")
                    
                    if event_type == "response.audio.delta":
                        audio_data = base64.b64decode(data["delta"])
                        self.play_audio(audio_data)
                    elif event_type == "response.text.delta":
                        self.logger.info(f"Text response: {data['delta']}")
                    elif event_type == "error":
                        self.logger.error(f"API Error: {data.get('error')}")
                        
        except Exception as e:
            self.logger.error(f"WebSocket error: {e}")
            self.session_ready = False
            self.reconnect_websocket()

    def connect_websocket(self):
        """Start WebSocket connection"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.ws_thread = threading.Thread(
            target=lambda: self.loop.run_until_complete(self.websocket_handler()),
            daemon=True
        )
        self.ws_thread.start()

    def reconnect_websocket(self):
        """Reconnect WebSocket if disconnected"""
        if not self.running:
            return
        time.sleep(2)  # Wait before reconnecting
        self.logger.info("Attempting to reconnect WebSocket")
        self.connect_websocket()

    def on_button_press(self):
        """Handle spacebar press to start/stop recording"""
        if not self.session_ready:
            self.logger.warning("Not ready to record")
            return
            
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        """Start audio recording and streaming"""
        if not hasattr(self, 'websocket'):
            self.logger.error("No WebSocket connection")
            return
            
        self.recording = True
        self.set_status("Listening", "Recording...")
        self.audio_thread = threading.Thread(target=self.stream_audio, daemon=True)
        self.audio_thread.start()

    def stream_audio(self):
        """Stream audio to WebSocket"""
        try:
            while self.recording and self.session_ready:
                audio_data = self.stream.read(1024, exception_on_overflow=False)
                audio_event = {
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(audio_data).decode('utf-8')
                }
                asyncio.run_coroutine_threadsafe(
                    self.websocket.send(json.dumps(audio_event)),
                    self.loop
                )
                
                # Trigger response generation
                response_event = {
                    "type": "response.create",
                    "response": {
                        "modalities": ["text", "audio"],
                        "instructions": "Respond naturally to the user's input"
                    }
                }
                asyncio.run_coroutine_threadsafe(
                    self.websocket.send(json.dumps(response_event)),
                    self.loop
                )
                
        except Exception as e:
            self.logger.error(f"Audio streaming error: {e}")
        finally:
            self.recording = False
            self.set_status("Processing", "Generating response...")

    def stop_recording(self):
        """Stop audio recording"""
        self.recording = False
        self.set_status("Processing", "Generating response...")

    def play_audio(self, audio_data):
        """Play received audio data"""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=1)
                
            sound = pygame.mixer.Sound(buffer=audio_data)
            sound.play()
            self.set_status("Speaking", "Playing response...")
            
            # Wait for playback to finish
            while pygame.mixer.get_busy():
                time.sleep(0.1)
                
            self.set_status("Ready", "Press SPACE to speak")
            
        except Exception as e:
            self.logger.error(f"Audio playback error: {e}")

    def set_status(self, status, message):
        """Update module status"""
        self.status = status
        self.status_message = message
        self.logger.info(f"Status: {status} - {message}")

    def draw(self, screen, position):
        """Draw module UI"""
        try:
            x, y = position['x'], position['y']
            width, height = position.get('width', 225), position.get('height', 200)
            
            pygame.draw.rect(screen, (30, 30, 40), (x, y, width, height))
            pygame.draw.rect(screen, (50, 50, 150), (x, y, width, height), 2)
            
            if not hasattr(self, 'font'):
                self.font = pygame.font.Font(None, 24)
                self.title_font = pygame.font.Font(None, 32)
                
            title = self.title_font.render("Voice AI", True, (150, 150, 255))
            screen.blit(title, (x + 10, y + 10))
            
            status_text = self.font.render(f"Status: {self.status}", True, (200, 200, 200))
            screen.blit(status_text, (x + 10, y + 50))
            
            if self.status_message:
                msg = self.status_message[:30] + "..." if len(self.status_message) > 30 else self.status_message
                msg_text = self.font.render(msg, True, (200, 200, 200))
                screen.blit(msg_text, (x + 10, y + 80))
                
            # Recording indicator
            if self.recording:
                pulse = int(128 + 127 * (pygame.time.get_ticks() % 1000) / 1000)
                pygame.draw.circle(screen, (255, pulse, pulse), (x + 20, y + 120), 8)
                screen.blit(self.font.render("Recording", True, (255, pulse, pulse)), (x + 35, y + 112))
                
        except Exception as e:
            self.logger.error(f"Draw error: {e}")

    def cleanup(self):
        """Clean up resources"""
        self.running = False
        if hasattr(self, 'websocket'):
            asyncio.run_coroutine_threadsafe(self.websocket.close(), self.loop)
        if hasattr(self, 'stream'):
            self.stream.stop_stream()
            self.stream.close()
        self.pyaudio.terminate()
        if hasattr(self, 'loop'):
            self.loop.call_soon_threadsafe(self.loop.stop)

if __name__ == "__main__":
    # Test the module
    config = {
        'openai': {'api_key': 'your-api-key-here'},
        'audio': {'device_index': 2}
    }
    pygame.init()
    screen = pygame.display.set_mode((800, 480))
    module = AIVoiceModule(config)
    
    running = True
    clock = pygame.time.Clock()
    
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                module.on_button_press()
                
        screen.fill((0, 0, 0))
        module.draw(screen, {'x': 10, 'y': 10})
        pygame.display.flip()
        clock.tick(30)
        
    module.cleanup()
    pygame.quit()