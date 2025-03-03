import json
import os
import pygame
import logging
import threading
import base64
import time
import subprocess
from queue import Queue
from config import CONFIG
import websocket

class AIVoiceModule:
    """
    Beta
    Build low-latency, multi-modal experiences with the Realtime API.
    The OpenAI Realtime API enables you to build low-latency, multi-modal conversational experiences 
    with expressive voice-enabled models. These models support realtime text and audio inputs 
    and outputs, voice activation detection, function calling, and much more.
    """

    def __init__(self, config):
        self.logger = logging.getLogger("AI_Voice")
        self.logger.info("Initializing AI Voice Module (Realtime API Beta)")
        
        self.config = config or {}
        self.status = "Initializing"
        self.status_message = "Starting voice systems..."
        self.recording = False
        self.processing = False
        self.session_ready = False
        self.running = True
        self.response_queue = Queue()
        self.audio_enabled = True
        self.audio_device = None
        
        self.sample_rate = 24000
        self.channels = 1
        self.format = 'S16_LE'
        self.chunk_size = 1024
        
        self.api_key = self.config.get('openai', {}).get('api_key')
        if not self.api_key:
            self.api_key = os.getenv('OPENAI_API_KEY') or os.getenv('OPENAI_VOICE_KEY')
            if not self.api_key:
                self.logger.error("No OpenAI API key found in config or environment")
                self.set_status("Error", "No API key")
                return
        
        self.ws_url = "wss://api.openai.com/v1/realtime"
        
        self.initialize()

    def initialize(self):
        self.logger.info("Starting AIVoiceModule initialization")
        print("MIRROR DEBUG: Starting AIVoiceModule initialization")
        try:
            self.test_api_connection()
            time.sleep(2)  # Wait for ALSA to stabilize
            self.check_alsa_sanity()
            if self.audio_enabled:
                self.test_audio_setup()
            self.connect_websocket_thread()
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
            if 'gpt-4o-realtime-preview-2024-12-17' in models:
                self.model = 'gpt-4o-realtime-preview-2024-12-17'
                self.logger.info("Confirmed access to gpt-4o-realtime-preview-2024-12-17")
            elif 'gpt-4o-mini-realtime-preview-2024-12-17' in models:
                self.model = 'gpt-4o-mini-realtime-preview-2024-12-17'
                self.logger.info("Confirmed access to gpt-4o-mini-realtime-preview-2024-12-17")
            else:
                self.model = 'gpt-4o-mini'
                self.logger.warning("Realtime models not available; using gpt-4o-mini")
        else:
            self.logger.error(f"API test failed: {response.status_code} - {response.text}")
            self.model = 'gpt-4o-mini'

    def check_alsa_sanity(self):
        """Pre-check ALSA configuration for recording devices"""
        try:
            self.logger.info(f"ALSA environment: {os.environ.get('ALSA_CONFIG_PATH', 'Not set')}")
            playback_result = subprocess.run(['aplay', '-l'], capture_output=True, text=True, timeout=5)
            if playback_result.returncode == 0:
                self.logger.info("ALSA playback devices:\n" + playback_result.stdout)
            else:
                self.logger.error(f"ALSA playback check failed: {playback_result.stderr}")
            
            record_result = subprocess.run(['arecord', '-l'], capture_output=True, text=True, timeout=5)
            if record_result.returncode == 0:
                self.logger.info("ALSA recording devices:\n" + record_result.stdout)
                if "card 3" in record_result.stdout.lower():
                    self.logger.info("Confirmed USB mic (card 3) is present for recording")
                else:
                    self.logger.warning("USB mic (card 3) not found in ALSA recording list")
            else:
                self.logger.error(f"ALSA recording check failed: {record_result.stderr}")
        except Exception as e:
            self.logger.error(f"ALSA sanity check failed: {e}")

    def test_audio_setup(self):
        """Test audio setup with arecord"""
        try:
            test_dir = "/home/dan/tmp"
            os.makedirs(test_dir, exist_ok=True)  # Create directory if it doesn’t exist
            test_file = os.path.join(test_dir, "test_rec.wav")
            time.sleep(2)  # Wait for ALSA to settle
            for attempt in range(3):
                self.logger.info(f"Audio test attempt {attempt + 1}/3")
                for device in ['safe_capture', 'hw:3,0', None]:
                    cmd = ['arecord', '-f', 'S16_LE', '-r', str(self.sample_rate), '-c', str(self.channels), '-d', '1', test_file]
                    if device:
                        cmd.extend(['-D', device])
                    self.logger.info(f"Testing device: {device or 'default'} with cmd: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if result.returncode == 0 and os.path.exists(test_file):
                        self.logger.info(f"Audio test successful with {device or 'default'}")
                        self.audio_device = device
                        os.remove(test_file)
                        return
                    else:
                        self.logger.warning(f"Audio test with {device or 'default'} failed: {result.stderr}")
                    time.sleep(1)
            self.logger.error("All audio tests failed after retries")
            self.audio_enabled = False
        except Exception as e:
            self.logger.error(f"Audio test setup failed: {e}")
            self.audio_enabled = False

    def on_ws_open(self, ws):
        self.logger.info("WebSocket connected")
        self.ws = ws

    def on_ws_message(self, ws, message):
        data = json.loads(message)
        event_type = data.get("type")
        self.logger.debug(f"WebSocket event: {event_type}")
        
        if event_type == "session.created":
            self.logger.info("Session created")
            self.session_ready = True
            ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "model": self.model,
                    "modalities": ["text", "audio"],
                    "instructions": "You are a helpful assistant for a smart mirror.",
                    "voice": "alloy",
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16"
                }
            }))
            self.logger.info("Session configured")
        elif event_type == "session.updated":
            self.logger.info("Session updated successfully")
        elif event_type == "response.audio.delta":
            audio_data = base64.b64decode(data["delta"])
            self.play_audio(audio_data)
        elif event_type == "response.text.delta":
            self.logger.info(f"Text: {data['delta']}")
        elif event_type == "response.done":
            self.logger.info("Response completed")
        elif event_type == "error":
            self.logger.error(f"API Error: {data.get('error')}")

    def on_ws_error(self, ws, error):
        self.logger.error(f"WebSocket error: {error}")
        self.session_ready = False
        self.reconnect_websocket()

    def on_ws_close(self, ws, close_status_code, close_msg):
        self.logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.session_ready = False
        self.reconnect_websocket()

    def connect_websocket_thread(self):
        headers = [
            f"Authorization: Bearer {self.api_key}",
            "OpenAI-Beta: realtime=v1"
        ]
        ws_url = f"{self.ws_url}?model={self.model}"
        self.ws_thread = threading.Thread(
            target=lambda: websocket.WebSocketApp(
                ws_url,
                header=headers,
                on_open=self.on_ws_open,
                on_message=self.on_ws_message,
                on_error=self.on_ws_error,
                on_close=self.on_ws_close
            ).run_forever(),
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
        self.connect_websocket_thread()

    def on_button_press(self):
        self.logger.info("Spacebar pressed")
        if not self.session_ready:
            self.logger.warning("WebSocket not ready")
            self.set_status("Error", "Not connected")
            return
        if not self.audio_enabled:
            self.logger.warning("Audio disabled, cannot record")
            return
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        if not hasattr(self, 'ws'):
            self.logger.error("No WebSocket connection")
            self.set_status("Error", "No connection")
            return
        self.recording = True
        self.set_status("Listening", "Recording...")
        self.logger.info("Starting recording")
        self.audio_thread = threading.Thread(target=self.stream_audio, daemon=True)
        self.audio_thread.start()

    def stream_audio(self):
        """Stream audio using arecord with dynamic device"""
        try:
            self.logger.info("Streaming audio with arecord")
            temp_dir = "/home/dan/tmp"
            os.makedirs(temp_dir, exist_ok=True)
            temp_file = os.path.join(temp_dir, "mirror_rec.wav")
            cmd = ['arecord', '-f', 'S16_LE', '-r', str(self.sample_rate), '-c', str(self.channels), temp_file]
            if self.audio_device:
                cmd.extend(['-D', self.audio_device])
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            start_time = time.time()
            while self.recording and self.session_ready and (time.time() - start_time) < 10:
                time.sleep(0.5)
            
            process.terminate()
            if os.path.exists(temp_file):
                with open(temp_file, 'rb') as f:
                    audio_data = f.read()
                os.remove(temp_file)
                
                if len(audio_data) > 44:  # Skip WAV header
                    audio_data = audio_data[44:]
                    audio_event = {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(audio_data).decode('utf-8')
                    }
                    self.ws.send(json.dumps(audio_event))
                    self.logger.debug("Audio sent")
                    
                    response_event = {
                        "type": "response.create",
                        "response": {
                            "modalities": ["text", "audio"],
                            "instructions": "Respond naturally"
                        }
                    }
                    self.ws.send(json.dumps(response_event))
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
            if isinstance(position, dict):
                x, y = position.get('x', 0), position.get('y', 0)
                width, height = position.get('width', 250), position.get('height', 200)
            else:
                x, y = position
                width, height = 250, 200
            
            pygame.draw.rect(screen, (30, 30, 40), (x, y, width, height))
            pygame.draw.rect(screen, (50, 50, 150), (x, y, width, height), 2)
            
            if not hasattr(self, 'font'):
                self.font = pygame.font.Font(None, 24)
                self.title_font = pygame.font.Font(None, 32)
                
            title = self.title_font.render("Voice AI (Beta)", True, (150, 150, 255))
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
        if hasattr(self, 'ws'):
            self.ws.close()
        self.logger.info("Cleanup complete")

if __name__ == "__main__":
    CONFIG = {
        'openai': {'api_key': 'your-api-key-here'},
        'audio': {'device_index': 3}
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