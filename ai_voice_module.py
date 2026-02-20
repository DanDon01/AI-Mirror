import json
import os
import pygame
import logging
import threading
import base64
import time
import subprocess
import shutil
from queue import Queue, Empty
import websocket
import wave

# Resolve project root directory for relative paths
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_PROJECT_DIR, "data")
_DEBUG_DIR = os.path.join(_DATA_DIR, "debug")
_RECORDINGS_DIR = os.path.join(_DATA_DIR, "recordings")
_TMP_DIR = os.path.join(_DATA_DIR, "tmp")


class AIVoiceModule:
    def __init__(self, config):
        self.logger = logging.getLogger("AI_Voice")
        self.logger.info("Initializing AI Voice Module (Realtime API)")

        self.config = config or {}
        self.status = "Initializing"
        self.status_message = "Starting voice systems..."
        self.recording = False
        self.processing = False
        self.session_ready = False
        self.running = True
        self.response_queue = Queue()
        self.audio_enabled = True
        self.audio_device = "hw:3,0"

        self.sample_rate = 24000
        self.record_rate = 44100
        self.channels = 1
        self.format = "S16_LE"
        self.chunk_size = 1024

        self.api_key = self.config.get("openai", {}).get("api_key")
        if not self.api_key:
            self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_VOICE_KEY")
            if not self.api_key:
                self.logger.error("No OpenAI API key found")
                self.set_status("Error", "No API key")
                return

        self.ws_url = "wss://api.openai.com/v1/realtime"
        self.send_queue = Queue()
        self.speech_detected = False
        self.buffer_committed = False
        self.transcript_received = False
        self.retry_count = 0
        self.reconnecting = False
        self.audio_chunks = []

        # Enable/disable debug file writing (disable in production to save disk)
        self.debug_write_enabled = self.config.get("debug_write", True)

        self.initialize()

    def initialize(self):
        self.logger.info("Starting AIVoiceModule initialization")
        try:
            self.test_api_connection()
            time.sleep(2)
            self.check_alsa_sanity()
            if self.audio_enabled:
                self.test_audio_setup()
            self.connect_websocket_thread()
            time.sleep(2)
            self.set_status("Ready", "Press SPACE to speak")
            self.logger.info("AIVoiceModule initialization complete")
        except Exception as e:
            self.logger.error(f"AIVoiceModule initialization failed: {e}")
            self.set_status("Error", f"Init failed: {str(e)}")
            raise

    def test_api_connection(self):
        import requests
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        response = requests.get("https://api.openai.com/v1/models", headers=headers)
        if response.status_code == 200:
            models = [m["id"] for m in response.json()["data"]]
            self.logger.info(f"Available models: {models}")
            self.model = "gpt-4o-realtime-preview"
            self.logger.info(f"Using model: {self.model}")
        else:
            self.logger.error(f"API test failed: {response.status_code} - {response.text}")
            self.model = "gpt-4o-realtime-preview"

    def check_alsa_sanity(self):
        try:
            self.logger.info(f"ALSA environment: {os.environ.get('ALSA_CONFIG_PATH', 'Not set')}")
            playback_result = subprocess.run(["aplay", "-l"], capture_output=True, text=True, timeout=5)
            if playback_result.returncode == 0:
                self.logger.info("ALSA playback devices:\n" + playback_result.stdout)
            else:
                self.logger.error(f"ALSA playback check failed: {playback_result.stderr}")

            record_result = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=5)
            if record_result.returncode == 0:
                self.logger.info("ALSA recording devices:\n" + record_result.stdout)
                if "card 3" in record_result.stdout.lower():
                    self.logger.info("Confirmed USB mic (card 3)")
                    return
                else:
                    self.logger.warning("USB mic (card 3) not found")
            else:
                self.logger.error(f"ALSA recording check failed: {record_result.stderr}")

            os.makedirs(_TMP_DIR, exist_ok=True)
            test_file = os.path.join(_TMP_DIR, "test_alsa_check.wav")
            env = os.environ.copy()
            env["ALSA_CONFIG_PATH"] = "/usr/share/alsa/alsa.conf"
            cmd = ["arecord", "-f", "S16_LE", "-r", "44100", "-c", "1", "-d", "1", test_file, "-D", self.audio_device]
            self.logger.info(f"Testing arecord: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=env)
            if result.returncode == 0 and os.path.exists(test_file):
                self.logger.info(f"ALSA test succeeded with {self.audio_device}")
                os.remove(test_file)
                return
            else:
                self.logger.error(f"ALSA test failed: {result.stderr}")
                self.audio_enabled = False
        except Exception as e:
            self.logger.error(f"ALSA sanity check failed: {e}")
            self.audio_enabled = False

    def test_audio_setup(self):
        try:
            os.makedirs(_TMP_DIR, exist_ok=True)
            test_file = os.path.join(_TMP_DIR, "test_rec.wav")
            time.sleep(2)
            env = os.environ.copy()
            env["ALSA_CONFIG_PATH"] = "/usr/share/alsa/alsa.conf"
            for attempt in range(3):
                self.logger.info(f"Audio test attempt {attempt + 1}/3")
                cmd = ["arecord", "-f", "S16_LE", "-r", "44100", "-c", str(self.channels), "-d", "1", test_file, "-D", self.audio_device]
                self.logger.info(f"Testing device: {self.audio_device} with cmd: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=env)
                if result.returncode == 0 and os.path.exists(test_file):
                    self.logger.info(f"Audio test successful with {self.audio_device}")
                    temp_file_resampled = os.path.join(_TMP_DIR, "test_rec_resampled.wav")
                    subprocess.run(["sox", test_file, "-r", "24000", temp_file_resampled], check=True, env=env)
                    os.remove(test_file)
                    os.rename(temp_file_resampled, test_file)
                    self.logger.info("Resampled test audio to 24000 Hz")
                    os.remove(test_file)
                    return
                else:
                    self.logger.warning(f"Audio test failed: {result.stderr}")
                time.sleep(1)
            self.logger.error("All audio tests failed")
            self.audio_enabled = False
        except Exception as e:
            self.logger.error(f"Audio test setup failed: {e}")
            self.audio_enabled = False

    def on_ws_open(self, ws):
        self.logger.info("WebSocket connected")
        self.ws = ws

    def on_ws_message(self, ws, message):
        try:
            data = json.loads(message)
            event_type = data.get("type")
            self.logger.info(f"WebSocket event received: {event_type}")

            if self.debug_write_enabled:
                os.makedirs(_DEBUG_DIR, exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S_%f")[:19]
                debug_file = os.path.join(_DEBUG_DIR, f"ws_message_{timestamp}_{event_type}.json")
                with open(debug_file, "w") as f:
                    json.dump(data, f, indent=2)

            if event_type == "session.created":
                self.logger.info("Session created")
                self.session_ready = True
                self.send_ws_message({
                    "type": "session.update",
                    "session": {
                        "model": self.model,
                        "modalities": ["text", "audio"],
                        "instructions": "You are a helpful assistant for a smart mirror. Always respond with both text and audio.",
                        "voice": "echo",
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16",
                        "input_audio_transcription": {"model": "whisper-1"},
                        "turn_detection": None
                    }
                })
                self.logger.info("Session configured with Whisper transcription")
            elif event_type == "session.updated":
                self.logger.info("Session updated successfully")
            elif event_type == "input_audio_buffer.speech_started":
                self.logger.info("Speech detected")
                self.speech_detected = True
            elif event_type == "input_audio_buffer.speech_stopped":
                self.logger.info("Speech stopped")
                self.speech_detected = False
            elif event_type == "input_audio_buffer.committed":
                self.logger.info("Audio buffer committed")
                self.buffer_committed = True
            elif event_type == "conversation.item.created":
                transcript = data["item"]["content"][0].get("transcript", "")
                self.logger.info(f"Transcript received: {transcript}")
                self.transcript_received = True
            elif event_type == "response.audio.delta":
                self.logger.info("Received audio delta")
                audio_data = base64.b64decode(data.get("delta", ""))
                self.logger.info(f"Decoded audio chunk: {len(audio_data)} bytes")

                if self.debug_write_enabled:
                    audio_dir = os.path.join(_RECORDINGS_DIR, "response_audio")
                    os.makedirs(audio_dir, exist_ok=True)
                    if not hasattr(self, "current_response_timestamp"):
                        self.current_response_timestamp = time.strftime("%Y%m%d_%H%M%S")
                        self.chunk_counter = 0
                    self.chunk_counter += 1
                    chunk_file = os.path.join(audio_dir, f"response_{self.current_response_timestamp}_chunk_{self.chunk_counter:03d}.raw")
                    with open(chunk_file, "wb") as f:
                        f.write(audio_data)
                    self.logger.info(f"Saved audio chunk to {chunk_file}")

                self.play_audio(audio_data)
            elif event_type == "response.text.delta":
                text = data.get("delta", "")
                self.logger.info(f"Received text delta: {text}")
            elif event_type == "response.done":
                self.logger.info("Response completed")
                self.logger.info(f"Full response data: {json.dumps(data, indent=2)}")
                if data.get("response", {}).get("status") == "failed" and "server_error" in json.dumps(data):
                    self.retry_count += 1
                    if self.retry_count <= 3:
                        self.logger.warning(f"Server error, retrying (attempt {self.retry_count}/3)")
                        self.retry_response_create()
                    else:
                        self.logger.error("Max retries reached, will reconnect on next failure")
                        self.retry_count = 0
                        self.set_status("Error", "Failed after retries")
                        threading.Thread(target=self.reconnect_websocket, daemon=True).start()
                else:
                    self.retry_count = 0
                if hasattr(self, "current_response_timestamp"):
                    del self.current_response_timestamp
                    del self.chunk_counter
                self.set_status("Ready", "Press SPACE to speak")
            elif event_type == "error":
                self.logger.error(f"API Error: {data.get('error')}")
        except Exception as e:
            self.logger.error(f"Error processing WebSocket message: {e}", exc_info=True)

    def retry_response_create(self):
        delay = 2 * self.retry_count
        self.logger.info(f"Retrying response.create in {delay}s (attempt {self.retry_count}/3)")
        time.sleep(delay)
        self.send_ws_message({"type": "input_audio_buffer.clear"})
        time.sleep(0.5)
        self.send_ws_message({
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": "Respond with audio and text to the user's query."
            }
        })
        self.set_status("Processing", f"Retrying AI response (attempt {self.retry_count}/3)...")

    def on_ws_error(self, ws, error):
        self.logger.error(f"WebSocket error: {error}")
        self.session_ready = False
        if not self.reconnecting:
            threading.Thread(target=self.reconnect_websocket, daemon=True).start()

    def on_ws_close(self, ws, close_status_code, close_msg):
        self.logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.session_ready = False
        if not self.reconnecting:
            threading.Thread(target=self.reconnect_websocket, daemon=True).start()

    def connect_websocket_thread(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
            "Sec-WebSocket-Protocol": "realtime"
        }
        ws_url = f"{self.ws_url}?model={self.model}"
        self.logger.info(f"Connecting to WebSocket URL: {ws_url}")

        self.ws = websocket.WebSocketApp(
            ws_url,
            header=headers,
            on_open=self.on_ws_open,
            on_message=self.on_ws_message,
            on_error=self.on_ws_error,
            on_close=self.on_ws_close
        )

        self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.ws_thread.start()
        self.ws_thread_send = threading.Thread(target=self._send_loop, daemon=True)
        self.ws_thread_send.start()
        self.logger.info("WebSocket threads started")

        start_time = time.time()
        while not self.session_ready and time.time() - start_time < 10:
            time.sleep(0.5)
        if not self.session_ready:
            self.logger.warning("WebSocket not ready after timeout")

    def _send_loop(self):
        while self.running:
            try:
                if not self.session_ready or not hasattr(self, "ws"):
                    time.sleep(0.1)
                    continue
                message = self.send_queue.get(timeout=1.0)
                self.ws.send(json.dumps(message))
                self.logger.info(f"Sent message: {message.get('type')}")
                self.send_queue.task_done()
            except Empty:
                continue
            except Exception as e:
                self.logger.error(f"Send loop error: {e}")
                if not self.reconnecting:
                    threading.Thread(target=self.reconnect_websocket, daemon=True).start()

    def send_ws_message(self, data):
        self.send_queue.put(data)

    def reconnect_websocket(self):
        if not self.running or self.reconnecting:
            return
        self.reconnecting = True
        self.logger.info("Reconnecting WebSocket...")
        if hasattr(self, "ws"):
            try:
                self.ws.close()
            except Exception:
                pass
        time.sleep(2)
        self.connect_websocket_thread()
        wait_time = 0
        while not self.session_ready and wait_time < 5:
            time.sleep(0.5)
            wait_time += 0.5
        if self.session_ready:
            self.logger.info("WebSocket reconnected successfully")
            self.set_status("Ready", "Press SPACE to speak")
        else:
            self.logger.error("Failed to reconnect WebSocket")
            self.set_status("Error", "Connection failed")
        self.reconnecting = False

    def on_button_press(self):
        self.logger.info("Spacebar pressed")
        if not self.session_ready:
            self.logger.warning("WebSocket not ready")
            self.set_status("Error", "Not connected")
            return
        if not self.audio_enabled:
            self.logger.warning("Audio disabled")
            return
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        if not hasattr(self, "ws"):
            self.logger.error("No WebSocket connection")
            self.set_status("Error", "No connection")
            return
        self.recording = True
        self.speech_detected = False
        self.buffer_committed = False
        self.transcript_received = False
        self.retry_count = 0
        self.audio_chunks = []
        self.set_status("Listening", "Recording...")
        self.logger.info("Starting recording")
        self.audio_thread = threading.Thread(target=self.stream_audio, daemon=True)
        self.audio_thread.start()

    def save_sent_audio(self, chunks, timestamp):
        """Save the exact audio sent to the API as a WAV file."""
        os.makedirs(_RECORDINGS_DIR, exist_ok=True)
        sent_audio_file = os.path.join(_RECORDINGS_DIR, f"sent_audio_{timestamp}.wav")

        pcm_data = b""
        for chunk in chunks:
            pcm_data += base64.b64decode(chunk["audio"])

        with wave.open(sent_audio_file, "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm_data)

        self.logger.info(f"Saved sent audio to {sent_audio_file} ({len(pcm_data)} bytes)")
        return sent_audio_file

    def stream_audio(self):
        """Stream audio to the Realtime API.

        NOTE: Currently uses a pre-recorded test WAV file for development.
        This will be replaced with live microphone recording when audio
        hardware setup on the Pi is finalized.
        """
        try:
            if not hasattr(self, "ws") or not self.session_ready:
                self.logger.error("No active WebSocket session")
                self.set_status("Error", "No connection")
                return

            # TODO: Replace with live microphone recording when Pi audio is ready.
            # For now, use a pre-recorded test file for development.
            test_audio_path = os.path.join(_DATA_DIR, "test_spedup.wav")
            if not os.path.exists(test_audio_path):
                self.logger.error(f"Test audio file not found: {test_audio_path}")
                self.set_status("Error", "No test audio file")
                return

            self.logger.info(f"Using pre-recorded audio: {test_audio_path}")
            with open(test_audio_path, "rb") as f:
                pcm_data = f.read()

            if len(pcm_data) > 4800:
                self.logger.info(f"PCM data size: {len(pcm_data)} bytes")
                chunk_size = 16000
                total_chunks = (len(pcm_data) + chunk_size - 1) // chunk_size
                for i in range(0, len(pcm_data), chunk_size):
                    chunk = pcm_data[i:i + chunk_size]
                    self.audio_chunks.append({
                        "audio": base64.b64encode(chunk).decode("utf-8"),
                        "size": len(chunk)
                    })
                    self.logger.info(f"Accumulated chunk {(i // chunk_size) + 1}/{total_chunks} ({len(chunk)} bytes)")

                if self.debug_write_enabled:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    self.save_sent_audio(self.audio_chunks, timestamp)

                self.send_ws_message({"type": "input_audio_buffer.clear"})
                time.sleep(0.5)
                for chunk in self.audio_chunks:
                    self.send_ws_message({
                        "type": "input_audio_buffer.append",
                        "audio": chunk["audio"]
                    })
                    self.logger.info(f"Sent chunk ({chunk['size']} bytes)")
                    time.sleep(0.25)

                self.send_ws_message({"type": "input_audio_buffer.commit"})
                self.logger.info("Audio buffer committed")
                time.sleep(1.0)
                self.send_ws_message({
                    "type": "response.create",
                    "response": {
                        "modalities": ["audio", "text"],
                        "instructions": "Respond with audio and text to the user's query."
                    }
                })
                self.logger.info("Response requested")
                self.set_status("Processing", "Waiting for AI response...")

        except Exception as e:
            self.logger.error(f"Streaming error: {str(e)}", exc_info=True)
            self.set_status("Error", f"Streaming failed: {str(e)}")
        finally:
            self.recording = False
            self.speech_detected = False
            self.buffer_committed = False
            self.transcript_received = False
            self.audio_chunks = []
            if not self.session_ready and not self.reconnecting:
                threading.Thread(target=self.reconnect_websocket, daemon=True).start()
            else:
                self.set_status("Processing", "Generating response...")

    def stop_recording(self):
        self.recording = False
        self.set_status("Processing", "Generating response...")
        self.logger.info("Recording stopped")

    def play_audio(self, audio_data):
        try:
            self.logger.info(f"Attempting to play {len(audio_data)} bytes")
            if len(audio_data) < 100:
                self.logger.warning(f"Audio data too small: {len(audio_data)} bytes")
                return

            if not pygame.mixer.get_init():
                try:
                    pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=1)
                    self.logger.info("Initialized pygame mixer: 24000 Hz, 16-bit, mono")
                except Exception as e:
                    self.logger.error(f"Failed to initialize pygame mixer: {e}")
                    return

            sound = pygame.mixer.Sound(buffer=audio_data)
            sound.play()
            self.set_status("Speaking", "Playing response...")
            self.logger.info("Audio playback started")

            start_time = time.time()
            while pygame.mixer.get_busy() and time.time() - start_time < 10:
                time.sleep(0.1)

            if pygame.mixer.get_busy():
                pygame.mixer.stop()
                self.logger.warning("Audio playback timed out")

            self.logger.info("Audio playback completed")
        except Exception as e:
            self.logger.error(f"Playback error: {e}", exc_info=True)

    def set_status(self, status, message):
        self.status = status
        self.status_message = message
        self.logger.info(f"Status: {status} - {message}")

    def draw(self, screen, position):
        try:
            if isinstance(position, dict):
                x, y = position.get("x", 0), position.get("y", 0)
                width, height = position.get("width", 250), position.get("height", 200)
            else:
                x, y = position
                width, height = 250, 200

            pygame.draw.rect(screen, (30, 30, 40), (x, y, width, height))
            pygame.draw.rect(screen, (50, 50, 150), (x, y, width, height), 2)

            if not hasattr(self, "font"):
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
        if hasattr(self, "ws"):
            try:
                self.ws.close()
            except Exception:
                pass
        if hasattr(self, "audio_thread") and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2)
        if hasattr(self, "ws_thread_send") and self.ws_thread_send.is_alive():
            self.ws_thread_send.join(timeout=2)
        if pygame.mixer.get_init():
            pygame.mixer.quit()
        self.logger.info("Cleanup complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    CONFIG = {
        "openai": {"api_key": "your-api-key-here"},
        "audio": {"device_index": 3}
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
        module.draw(screen, {"x": 10, "y": 10})
        pygame.display.flip()
        clock.tick(30)
    module.cleanup()
    pygame.quit()
