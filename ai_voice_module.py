import asyncio
import websockets
import json
import os
import pygame
import logging
import threading
import base64
import time
import pyaudio
from queue import Queue
from config import CONFIG
import subprocess

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
        
        self.sample_rate = 24000
        self.channels = 1
        self.format = pyaudio.paInt16
        self.chunk_size = 1024
        
        self.api_key = self.config.get('openai', {}).get('api_key')
        if not self.api_key:
            self.api_key = os.getenv('OPENAI_API_KEY') or os.getenv('OPENAI_VOICE_KEY')
            if not self.api_key:
                self.logger.error("No OpenAI API key found in config or environment")
                self.set_status("Error", "No API key")
                return
        
        self.ws_url = "wss://api.openai.com/v1/realtime"
        self.pyaudio = None  # Initialize later in setup_audio
        
        threading.Thread(target=self.initialize, daemon=True).start()

    def initialize(self):
        self.logger.info("Starting AIVoiceModule initialization")
        print("MIRROR DEBUG: Starting AIVoiceModule initialization")
        try:
            self.test_api_connection()
            self.check_alsa_sanity()
            self.setup_audio()
            self.connect_websocket()
            self.set_status("Ready", "Press SPACE to speak")
            self.logger.info("AIVoiceModule initialization complete")
            print("MIRROR DEBUG: AIVoiceModule initialization complete")
        except Exception as e:
            self.logger.error(f"AIVoiceModule initialization failed: {e}")
            self.set_status("Error", f"Init failed: {str(e)}")
            print(f"MIRROR DEBUG: ❌ AIVoiceModule initialization failed: {e}")
            raise

    def test_api_connection(self):
        """Verify Realtime API access"""
        import requests
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        response = requests.get("https://api.openai.com/v1/models", headers=headers)
        if response.status_code == 200:
            models = [m['id'] for m in response.json()['data']]
            self.logger.info(f"Available models: {models}")
            if 'gpt-4o' in models:
                self.logger.info("Confirmed access to gpt-4o")
            else:
                self.logger.warning("gpt-4o not available; using available model")
        else:
            self.logger.error(f"API test failed: {response.status_code} - {response.text}")

    def check_alsa_sanity(self):
        """Pre-check ALSA configuration"""
        try:
            result = subprocess.run(['aplay', '-l'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.logger.info("ALSA device list: " + result.stdout)
                if "card 2" in result.stdout.lower():
                    self.logger.info("Confirmed USB mic (card 2) is present")
                else:
                    self.logger.warning("USB mic (card 2) not found in ALSA list")
            else:
                self.logger.error(f"ALSA check failed: {result.stderr}")
        except Exception as e:
            self.logger.error(f"ALSA sanity check failed: {e}")

    def setup_audio(self):
        """Setup audio input with robust device handling"""
        try:
            # Small delay to avoid race conditions with ALSA
            time.sleep(1)
            
            self.pyaudio = pyaudio.PyAudio()
            self.logger.info("Available audio devices:")
            usb_device_index = None
            for i in range(self.pyaudio.get_device_count()):
                device_info = self.pyaudio.get_device_info_by_index(i)
                self.logger.info(f"Device {i}: {device_info['name']}, Input Channels: {device_info['maxInputChannels']}")
                if 'usb' in device_info['name'].lower() and device_info['maxInputChannels'] > 0:
                    usb_device_index = i

            self.input_device_index = self.config.get('audio', {}).get('device_index', 2)
            if usb_device_index is not None and self.input_device_index != usb_device_index:
                self.logger.warning(f"Configured device_index {self.input_device_index} may not be USB mic; found USB at {usb_device_index}")
                self.input_device_index = usb_device_index
            elif self.pyaudio.get_device_count() == 0:
                self.logger.error("No audio devices available")
                raise Exception("No audio devices found")
            
            try:
                self.stream = self.pyaudio.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=self.input_device_index,
                    frames_per_buffer=self.chunk_size
                )
                self.logger.info(f"Audio stream opened with device index {self.input_device_index}")
            except ValueError as e:
                self.logger.warning(f"Device index {self.input_device_index} invalid, trying default device: {e}")
                self.stream = self.pyaudio.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.chunk_size
                )
                self.input_device_index = None
                self.logger.info("Audio stream opened with default device")
        except Exception as e:
            self.logger.error(f"Audio setup failed: {e}")
            self.set_status("Error", "Audio setup failed")
            if self.pyaudio:
                self.pyaudio.terminate()
                self.pyaudio = None
            raise

    async def websocket_handler(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        
        try:
            self.logger.info("Connecting to WebSocket")
            async with websockets.connect(self.ws_url, extra_headers=headers) as websocket:
                self.websocket = websocket
                self.session_ready = True
                self.logger.info("WebSocket connected")
                
                await websocket.send(json.dumps({
                    "type": "session.update",
                    "session": {
                        "model": "gpt-4o-mini",  # Use available model
                        "modalities": ["text", "audio"],
                        "instructions": "You are a helpful assistant for a smart mirror.",
                        "voice": "alloy",
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16"
                    }
                }))
                self.logger.info("Session configured")
                
                async for message in websocket:
                    data = json.loads(message)
                    event_type = data.get("type")
                    self.logger.debug(f"WebSocket event: {event_type}")
                    
                    if event_type == "response.audio.delta":
                        audio_data = base64.b64decode(data["delta"])
                        self.play_audio(audio_data)
                    elif event_type == "response.text.delta":
                        self.logger.info(f"Text: {data['delta']}")
                    elif event_type == "error":
                        self.logger.error(f"API Error: {data.get('error')}")
        except Exception as e:
            self.logger.error(f"WebSocket error: {e}")
            self.session_ready = False
            self.reconnect_websocket()

    def connect_websocket(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.ws_thread = threading.Thread(
            target=lambda: self.loop.run_until_complete(self.websocket_handler()),
            daemon=True
        )
        self.ws_thread.start()
        self.logger.info("WebSocket thread started")
        time.sleep(2)
        if not self.session_ready:
            self.logger.warning("WebSocket not ready after initialization")

    def reconnect_websocket(self):
        if not self.running:
            return
        self.logger.info("Reconnecting WebSocket...")
        time.sleep(2)
        self.connect_websocket()

    def on_button_press(self):
        self.logger.info("Spacebar pressed")
        if not self.session_ready:
            self.logger.warning("WebSocket not ready")
            self.set_status("Error", "Not connected")
            return
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        if not hasattr(self, 'websocket'):
            self.logger.error("No WebSocket connection")
            self.set_status("Error", "No connection")
            return
        self.recording = True
        self.set_status("Listening", "Recording...")
        self.logger.info("Starting recording")
        self.audio_thread = threading.Thread(target=self.stream_audio, daemon=True)
        self.audio_thread.start()

    def stream_audio(self):
        try:
            self.logger.info("Streaming audio")
            while self.recording and self.session_ready:
                audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                self.logger.debug(f"Captured {len(audio_data)} bytes")
                if len(audio_data) > 0:
                    audio_event = {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(audio_data).decode('utf-8')
                    }
                    asyncio.run_coroutine_threadsafe(
                        self.websocket.send(json.dumps(audio_event)),
                        self.loop
                    )
                    self.logger.debug("Audio sent")
                    
                    response_event = {
                        "type": "response.create",
                        "response": {
                            "modalities": ["text", "audio"],
                            "instructions": "Respond naturally"
                        }
                    }
                    asyncio.run_coroutine_threadsafe(
                        self.websocket.send(json.dumps(response_event)),
                        self.loop
                    )
                    self.logger.debug("Response requested")
        except Exception as e:
            self.logger.error(f"Streaming error: {e}")
        finally:
            self.recording = False
            self.set_status("Processing", "Generating response...")

    def stop_recording(self):
        self.recording = False
        self.set_status("Processing", "Generating response...")
        self.logger.info("Recording stopped")

    def play_audio(self, audio_data):
        try:
            self.logger.info(f"Playing {len(audio_data)} bytes")
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=1)
            sound = pygame.mixer.Sound(buffer=audio_data)
            sound.play()
            self.set_status("Speaking", "Playing response...")
            while pygame.mixer.get_busy():
                time.sleep(0.1)
            self.set_status("Ready", "Press SPACE to speak")
        except Exception as e:
            self.logger.error(f"Playback error: {e}")

    def set_status(self, status, message):
        self.status = status
        self.status_message = message
        self.logger.info(f"Status: {status} - {message}")

    def draw(self, screen, position):
        try:
            x, y = position['x'], position['y']
            width, height = position.get('width', 250), position.get('height', 200)
            pygame.draw.rect(screen, (30, 30, 40), (x, y, width, height))
            pygame.draw.rect(screen, (50, 50, 150), (x, y, width, height), 2)
            
            if not hasattr(self, 'font'):
                self.font = pygame.font.Font(None, 24)
                self.title_font = pygame.font.Font(None, 32)
                
            title = self.title_font.render("Voice AI", True, (150, 150, 255))
            screen.blit(title, (x + 10, y + 10))
            status_text = self.font.render(f"Status: {self.status}", True, (200, 200, 200))
            screen.blit(status_text, (x + 10, y + 50))
            msg = self.status_message[:30] + "..." if len(self.status_message) > 30 else self.status_message
            screen.blit(self.font.render(msg, True, (200, 200, 200)), (x + 10, y + 80))
            
            if self.recording:
                pulse = int(128 + 127 * (pygame.time.get_ticks() % 1000) / 1000)
                pygame.draw.circle(screen, (255, pulse, pulse), (x + 20, y + 120), 8)
                screen.blit(self.font.render("Recording", True, (255, pulse, pulse)), (x + 35, y + 112))
        except Exception as e:
            self.logger.error(f"Draw error: {e}")

    def cleanup(self):
        self.running = False
        if hasattr(self, 'websocket'):
            asyncio.run_coroutine_threadsafe(self.websocket.close(), self.loop)
        if hasattr(self, 'stream'):
            self.stream.stop_stream()
            self.stream.close()
        if hasattr(self, 'pyaudio') and self.pyaudio:
            self.pyaudio.terminate()
        if hasattr(self, 'loop'):
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.logger.info("Cleanup complete")

if __name__ == "__main__":
    CONFIG = {
        'openai': {'api_key': 'your-api-key-here'},
        'audio': {'device_index': 2}
    }
    pygame.init()
    screen = pygame.display.set_mode((800, 480))
    module = AIVoiceModule(CONFIG)
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