import json
import os
import pygame
import logging
import threading
import base64
import time
import subprocess
import shutil
from queue import Queue
import websocket

class AIVoiceModule:
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
        self.audio_device = "hw:3,0"
        
        self.sample_rate = 24000  # API expects 24000 Hz
        self.record_rate = 44100  # Your mic records at 44100 Hz
        self.channels = 1
        self.format = "S16_LE"
        self.chunk_size = 1024
        
        self.api_key = self.config.get("openai", {}).get("api_key")
        if not self.api_key:
            self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_VOICE_KEY")
            if not self.api_key:
                self.logger.error("No OpenAI API key found in config or environment")
                self.set_status("Error", "No API key")
                return
        
        self.ws_url = "wss://api.openai.com/v1/realtime"
        self.send_queue = Queue()  # For thread-safe WebSocket sending
        
        self.initialize()

    def initialize(self):
        self.logger.info("Starting AIVoiceModule initialization")
        print("MIRROR DEBUG: Starting AIVoiceModule initialization")
        try:
            self.test_api_connection()
            time.sleep(2)
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
            models = [m["id"] for m in response.json()["data"]]
            self.logger.info(f"Available models: {models}")
            self.model = "gpt-4o-realtime-preview-2024-12-17"
            self.logger.info("Using gpt-4o-realtime-preview-2024-12-17")
        else:
            self.logger.error(f"API test failed: {response.status_code} - {response.text}")
            self.model = "gpt-4o-realtime-preview-2024-12-17"

    def check_alsa_sanity(self):
        """Pre-check ALSA configuration for recording devices"""
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
                    self.logger.info("Confirmed USB mic (card 3) is present for recording")
                    return
                else:
                    self.logger.warning("USB mic (card 3) not found in ALSA recording list")
                    # Test arecord to confirm device functionality despite listing issue
                    test_file = "/home/dan/tmp/test_alsa_check.wav"
                    cmd = ["arecord", "-f", "S16_LE", "-r", "44100", "-c", "1", "-d", "1", test_file, "-D", self.audio_device]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if result.returncode == 0 and os.path.exists(test_file):
                        self.logger.info(f"ALSA test recording succeeded with {self.audio_device}, proceeding despite listing issue")
                        os.remove(test_file)
                        return
                    else:
                        self.logger.error(f"ALSA test recording failed: {result.stderr}")
            else:
                self.logger.error(f"ALSA recording check failed: {record_result.stderr}")
            self.logger.error("Failed to confirm USB mic functionality")
            self.audio_enabled = False
        except Exception as e:
            self.logger.error(f"ALSA sanity check failed: {e}")
            self.audio_enabled = False

    def test_audio_setup(self):
        """Test audio setup with arecord"""
        try:
            test_dir = "/home/dan/tmp"
            os.makedirs(test_dir, exist_ok=True)
            test_file = os.path.join(test_dir, "test_rec.wav")
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
                    temp_file_resampled = os.path.join(test_dir, "test_rec_resampled.wav")
                    subprocess.run(["sox", test_file, "-r", "24000", temp_file_resampled], check=True, env=env)
                    os.remove(test_file)
                    os.rename(temp_file_resampled, test_file)
                    self.logger.info("Resampled test audio to 24000 Hz")
                    os.remove(test_file)
                    return
                else:
                    self.logger.warning(f"Audio test with {self.audio_device} failed: {result.stderr}")
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
        try:
            data = json.loads(message)
            event_type = data.get("type")
            self.logger.info(f"WebSocket event received: {event_type}")
            
            # Save raw message for debugging
            debug_dir = "/home/dan/mirror_debug"
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S_%f")[:19]
            with open(f"{debug_dir}/ws_message_{timestamp}_{event_type}.json", "w") as f:
                json.dump(data, f, indent=2)
            
            if event_type == "session.created":
                self.logger.info("Session created")
                self.session_ready = True
                self.send_ws_message({
                    "type": "session.update",
                    "session": {
                        "model": self.model,
                        "modalities": ["text", "audio"],
                        "instructions": "You are a helpful assistant for a smart mirror. Respond with both text and audio.",
                        "voice": "alloy",
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16"
                    }
                })
                self.logger.info("Session configured")
            elif event_type == "session.updated":
                self.logger.info("Session updated successfully")
            elif event_type == "response.audio.delta":
                self.logger.info("Received audio delta from API")
                audio_data = base64.b64decode(data.get("delta", ""))
                self.logger.info(f"Decoded audio chunk: {len(audio_data)} bytes")
                audio_dir = "/home/dan/mirror_recordings/response_audio"
                os.makedirs(audio_dir, exist_ok=True)
                if not hasattr(self, "current_response_timestamp"):
                    self.current_response_timestamp = time.strftime("%Y%m%d_%H%M%S")
                    self.chunk_counter = 0
                self.chunk_counter += 1
                chunk_file = f"{audio_dir}/response_{self.current_response_timestamp}_chunk_{self.chunk_counter:03d}.raw"
                with open(chunk_file, "wb") as f:
                    f.write(audio_data)
                self.logger.info(f"Saved audio chunk to {chunk_file}")
                self.play_audio(audio_data)
            elif event_type == "response.text.delta":
                text = data.get("delta", "")
                self.logger.info(f"Received text delta: {text}")
            elif event_type == "response.done":
                self.logger.info("Response completed")
                if hasattr(self, "current_response_timestamp"):
                    del self.current_response_timestamp
                    del self.chunk_counter
                self.set_status("Ready", "Press SPACE to speak")
            elif event_type == "error":
                self.logger.error(f"API Error: {data.get('error')}")
        except Exception as e:
            self.logger.error(f"Error processing WebSocket message: {e}", exc_info=True)

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
            self.logger.warning("WebSocket not ready after initialization timeout")

    def _send_loop(self):
        """Handles sending messages from the queue."""
        while self.running:
            try:
                if not self.session_ready or not hasattr(self, "ws"):
                    time.sleep(0.1)
                    continue
                message = self.send_queue.get(timeout=1.0)
                self.ws.send(json.dumps(message))
                self.logger.info(f"Sent message: {message.get('type')}")
                self.send_queue.task_done()
            except Queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Send loop error: {e}")
                self.reconnect_websocket()

    def send_ws_message(self, data):
        """Enqueue a message to be sent."""
        self.send_queue.put(data)

    def reconnect_websocket(self):
        if not self.running:
            return
        self.logger.info("Reconnecting WebSocket...")
        if hasattr(self, "ws"):
            try:
                self.ws.close()
            except:
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
        if not hasattr(self, "ws"):
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
            if not hasattr(self, "ws") or not self.session_ready:
                self.logger.error("No active WebSocket session before recording")
                self.set_status("Error", "No connection")
                return
                
            self.logger.info("Streaming audio with arecord")
            temp_dir = "/home/dan/tmp"
            recordings_dir = "/home/dan/mirror_recordings"
            os.makedirs(temp_dir, exist_ok=True)
            os.makedirs(recordings_dir, exist_ok=True)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            temp_file_raw = os.path.join(temp_dir, f"mirror_rec_{timestamp}.wav")
            saved_file = os.path.join(recordings_dir, f"recording_{timestamp}.wav")
            
            env = os.environ.copy()
            env["ALSA_CONFIG_PATH"] = ["/usr/share/alsa/alsa.conf"]
            
            min_record_time = 5
            cmd = ["arecord", "-f", "S16_LE", "-r", "44100", "-c", "1", temp_file_raw, "-D", self.audio_device]
            self.logger.info(f"Running arecord command: {' '.join(cmd)}")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            
            start_time = time.time()
            while self.recording and self.session_ready and (time.time() - start_time) < 60:
                elapsed = time.time() - start_time
                if elapsed < min_record_time:
                    self.set_status("Listening", f"Recording... ({min_record_time-elapsed:.1f}s)")
                else:
                    self.set_status("Listening", "Recording... (press SPACE to stop)")
                time.sleep(0.1)
            
            process.terminate()
            process.wait(timeout=2)
            
            if os.path.exists(temp_file_raw):
                file_size = os.path.getsize(temp_file_raw)
                self.logger.info(f"Raw recording: {temp_file_raw} ({file_size} bytes)")
                shutil.copy2(temp_file_raw, saved_file)
                self.logger.info(f"Saved copy of recording to: {saved_file}")
                
                temp_file_pcm = os.path.join(temp_dir, f"mirror_rec_{timestamp}.raw")
                convert_cmd = [
                    "sox", temp_file_raw,
                    "-r", str(self.sample_rate),
                    "-c", "1",
                    "-b", "16",
                    "-e", "signed-integer",
                    "-t", "raw",
                    temp_file_pcm
                ]
                self.logger.info(f"Converting audio: {' '.join(convert_cmd)}")
                result = subprocess.run(convert_cmd, capture_output=True, text=True, env=env)
                if result.returncode != 0:
                    self.logger.error(f"Audio conversion failed: {result.stderr}")
                    return
                
                pcm_saved = os.path.join(recordings_dir, f"recording_pcm_{timestamp}.raw")
                shutil.copy2(temp_file_pcm, pcm_saved)
                self.logger.info(f"Saved PCM data: {pcm_saved} ({os.path.getsize(temp_file_pcm)} bytes)")
                
                with open(temp_file_pcm, "rb") as f:
                    pcm_data = f.read()
                    
                if len(pcm_data) > 4800:
                    self.logger.info(f"PCM data size: {len(pcm_data)} bytes")
                    self.send_ws_message({"type": "input_audio_buffer.clear"})
                    time.sleep(0.2)
                    
                    chunk_size = 16000
                    for i in range(0, len(pcm_data), chunk_size):
                        if not self.session_ready:
                            self.logger.error("WebSocket connection lost")
                            break
                        chunk = pcm_data[i:i + chunk_size]
                        audio_event = {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(chunk).decode("utf-8")
                        }
                        self.send_ws_message(audio_event)
                        self.logger.info(f"Audio chunk {(i // chunk_size) + 1}/{len(pcm_data) // chunk_size + 1} sent ({len(chunk)} bytes)")
                        time.sleep(0.1)
                    
                    time.sleep(0.5)
                    self.send_ws_message({"type": "input_audio_buffer.commit"})
                    self.logger.info("Audio buffer committed")
                    time.sleep(1.0)
                    self.send_ws_message({
                        "type": "response.create",
                        "response": {"modalities": ["text", "audio"]}
                    })
                    self.logger.info("Response requested from API")
                    self.set_status("Processing", "Waiting for AI response...")
                
                for f in [temp_file_raw, temp_file_pcm]:
                    if os.path.exists(f):
                        os.remove(f)
            else:
                self.logger.error(f"Raw recording file not found: {temp_file_raw}")
                
        except Exception as e:
            self.logger.error(f"Streaming error: {str(e)}", exc_info=True)
            self.set_status("Error", f"Streaming failed: {str(e)}")
        finally:
            self.recording = False
            if not self.session_ready:
                self.reconnect_websocket()
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
                self.logger.warning(f"Audio data too small to play: {len(audio_data)} bytes")
                return
                
            if not pygame.mixer.get_init():
                try:
                    pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=1)
                    self.logger.info("Initialized pygame mixer with 24000 Hz, 16-bit, mono")
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
        if hasattr(self, "ws"):
            try:
                self.ws.close()
            except:
                pass
        if hasattr(self, "audio_thread") and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2)
        if self.ws_thread_send and self.ws_thread_send.is_alive():
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