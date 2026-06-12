"""Realtime voice module for AI-Mirror (OpenAI Realtime API, GA interface).

Speech-to-speech conversation over a single WebSocket using the GA
protocol (no beta header; session.type = "realtime"; GA event names).

Conversation flow (live microphone):
  - SPACE starts a conversation: the USB mic streams continuously to the
    API and server-side semantic VAD detects when you finish speaking,
    commits the audio and generates a reply - no push-to-talk per turn.
  - While the mirror is speaking the mic is gated (chunks dropped) so it
    does not hear its own speaker. No barge-in for now.
  - SPACE again ends the conversation; it also ends itself after
    conversation_timeout seconds without voice activity.

Microphone capture shells out to arecord with a plughw: device so ALSA
resamples the USB mic to the API's native 24 kHz mono S16_LE (raw hw:
devices usually cannot do 24 kHz). On hosts without arecord (Windows
dev box) or with no working mic, the module falls back to streaming the
pre-recorded test WAV with manual commit, so development still works.

Default model is gpt-realtime-mini (best cost/latency for casual mirror
conversation); set 'model' in config to gpt-realtime-2 for the smartest
voice with reasoning.

Avatar integration:
  set_audio_sink(fn)      - fn(pcm_bytes) called as audio chunks reach playback
  set_state_listener(fn)  - fn(status) called on every status change
"""

import json
import os
import pygame
import logging
import shutil
import threading
import base64
import time
import subprocess
from queue import Queue, Empty
import websocket

from api_tracker import api_tracker

# Resolve project root directory for relative paths
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_PROJECT_DIR, "data")
_DEBUG_DIR = os.path.join(_DATA_DIR, "debug")

DEFAULT_MODEL = "gpt-realtime-mini"
DEFAULT_VOICE = "marin"
DEFAULT_CAPTURE_DEVICE = "plughw:3,0"  # plughw = ALSA converts rate/format
SESSION_INSTRUCTIONS = (
    "You are a helpful assistant living inside a smart mirror in a hallway. "
    "Keep replies short, natural and conversational - one or two sentences "
    "unless asked for detail."
)
# Cost estimate for the api_tracker daily budget: gpt-realtime-mini audio
# runs ~10 tokens/sec, so a response second costs roughly $0.0002 out plus
# input context - call it $0.0005/sec all-in, with a small floor per turn.
EST_COST_PER_RESPONSE_SECOND = 0.0005
MIN_RESPONSE_COST = 0.003

MIC_CHUNK_SEC = 0.1       # mic read size (100 ms per append event)
UNMUTE_TAIL_SEC = 0.35    # keep mic gated briefly after playback ends
LIMIT_CHECK_EVERY_SEC = 5  # re-check rate limits mid-conversation


class AIVoiceModule:
    def __init__(self, config):
        self.logger = logging.getLogger("AI_Voice")
        self.logger.info("Initializing AI Voice Module (Realtime API, GA)")

        self.config = config or {}
        openai_cfg = self.config.get("openai", {})
        audio_cfg = self.config.get("audio", {})
        self.status = "Initializing"
        self.status_message = "Starting voice systems..."
        self.recording = False
        self.session_ready = False
        self.running = True
        self.audio_enabled = True
        self.capture_device = audio_cfg.get("alsa_device", DEFAULT_CAPTURE_DEVICE)
        self.conversation_timeout = audio_cfg.get("conversation_timeout", 25)
        self.max_conversation_sec = audio_cfg.get("max_conversation_seconds", 180)

        self.sample_rate = 24000  # Realtime API native PCM rate
        self.channels = 1

        self.api_key = openai_cfg.get("api_key")
        if not self.api_key:
            self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_VOICE_KEY")
            if not self.api_key:
                self.logger.error("No OpenAI API key found")
                self.set_status("Error", "No API key")
                return

        self.model = openai_cfg.get("model") or DEFAULT_MODEL
        self.voice = openai_cfg.get("voice") or DEFAULT_VOICE
        self.ws_url = f"wss://api.openai.com/v1/realtime?model={self.model}"

        self.send_queue = Queue()
        self.retry_count = 0
        self.reconnecting = False

        # Live conversation state
        self.live_mic = False           # determined during init
        self.conversation_active = False
        self._mic_proc = None
        self._mic_thread = None
        self._last_voice_activity = 0.0
        self._conversation_started = 0.0
        self._playback_active = False   # echo gate: mute mic while speaking
        self._mute_until = 0.0
        self._response_audio_bytes = 0  # for per-response cost estimation

        # Playback pipeline: audio deltas land here, a dedicated thread
        # feeds them to a pygame channel back-to-back for gapless speech
        self._playback_queue = Queue()
        self._playback_thread = None

        # Avatar hooks
        self._audio_sink = None
        self._state_listener = None
        # Mirror command hook: receives each user speech transcript
        self._command_listener = None

        # Debug file writing is expensive on the Pi SD card; opt-in only
        self.debug_write_enabled = self.config.get("debug_write", False)

        self.initialize()

    # ------------------------------------------------------------------
    # Avatar integration
    # ------------------------------------------------------------------

    def set_audio_sink(self, callback):
        """Register fn(pcm_bytes) called as audio chunks reach playback."""
        self._audio_sink = callback

    def set_state_listener(self, callback):
        """Register fn(status_string) called on every status change."""
        self._state_listener = callback

    def set_command_listener(self, callback):
        """Register fn(transcript) called with each user utterance, so the
        mirror can act on spoken commands (show/hide modules, dashboard)."""
        self._command_listener = callback

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self):
        self.logger.info("Starting AIVoiceModule initialization")
        try:
            self.check_alsa_sanity()
            self.live_mic = bool(
                self.audio_enabled and shutil.which("arecord")
            )
            if self.live_mic:
                self.logger.info(
                    f"Live microphone mode: device={self.capture_device}, "
                    f"server VAD handles turn-taking"
                )
            else:
                self.logger.warning(
                    "No usable microphone/arecord - falling back to test "
                    "WAV input (manual commit mode)"
                )
            self.connect_websocket_thread()
            self._playback_thread = threading.Thread(
                target=self._playback_loop, daemon=True, name="voice-playback"
            )
            self._playback_thread.start()
            self.set_status("Ready", "Press SPACE to talk")
            self.logger.info("AIVoiceModule initialization complete")
        except Exception as e:
            self.logger.error(f"AIVoiceModule initialization failed: {e}")
            self.set_status("Error", f"Init failed: {str(e)}")
            raise

    def check_alsa_sanity(self):
        """Verify ALSA recording devices exist (Pi only; skipped on Windows)."""
        if os.name == "nt":
            self.logger.info("Windows host: no ALSA, live mic disabled")
            self.audio_enabled = False
            return
        try:
            record_result = subprocess.run(
                ["arecord", "-l"], capture_output=True, text=True, timeout=5
            )
            if record_result.returncode == 0:
                self.logger.info("ALSA recording devices:\n" + record_result.stdout)
            else:
                self.logger.warning(f"ALSA recording check failed: {record_result.stderr}")
                self.audio_enabled = False
        except Exception as e:
            self.logger.warning(f"ALSA sanity check failed: {e}")
            self.audio_enabled = False

    # ------------------------------------------------------------------
    # WebSocket lifecycle (GA protocol)
    # ------------------------------------------------------------------

    def connect_websocket_thread(self):
        headers = [f"Authorization: Bearer {self.api_key}"]
        self.logger.info(f"Connecting to Realtime API: model={self.model}")

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            header=headers,
            on_open=self.on_ws_open,
            on_message=self.on_ws_message,
            on_error=self.on_ws_error,
            on_close=self.on_ws_close,
        )

        self.ws_thread = threading.Thread(
            target=self.ws.run_forever, daemon=True, name="voice-ws"
        )
        self.ws_thread.start()
        self.ws_thread_send = threading.Thread(
            target=self._send_loop, daemon=True, name="voice-ws-send"
        )
        self.ws_thread_send.start()

        start_time = time.time()
        while not self.session_ready and time.time() - start_time < 10:
            time.sleep(0.25)
        if not self.session_ready:
            self.logger.warning("Realtime session not ready after timeout")

    def on_ws_open(self, ws):
        self.logger.info("WebSocket connected")
        self.ws = ws

    def _session_config(self):
        """GA session.update payload (note required type: 'realtime').

        Live mic mode lets the server's semantic VAD detect end of
        speech, commit the buffer and create the response by itself.
        Test-WAV fallback keeps manual commit (turn_detection None).
        """
        if self.live_mic:
            turn_detection = {"type": "semantic_vad", "create_response": True}
        else:
            turn_detection = None
        return {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "output_modalities": ["audio"],
                "instructions": SESSION_INSTRUCTIONS,
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": self.sample_rate},
                        "transcription": {"model": "gpt-4o-transcribe"},
                        "turn_detection": turn_detection,
                    },
                    "output": {
                        "format": {"type": "audio/pcm", "rate": self.sample_rate},
                        "voice": self.voice,
                    },
                },
            },
        }

    def on_ws_message(self, ws, message):
        try:
            data = json.loads(message)
            event_type = data.get("type")

            if self.debug_write_enabled:
                self._write_debug_event(event_type, data)

            if event_type == "session.created":
                self.logger.info("Realtime session created")
                self.session_ready = True
                self.send_ws_message(self._session_config())
            elif event_type == "session.updated":
                self.logger.info("Session configured")
            elif event_type == "input_audio_buffer.speech_started":
                self._last_voice_activity = time.time()
                if self.conversation_active:
                    self.set_status("Listening", "Hearing you...")
            elif event_type == "input_audio_buffer.speech_stopped":
                self._last_voice_activity = time.time()
            elif event_type == "input_audio_buffer.committed":
                self.logger.info("Audio buffer committed")
                if self.conversation_active:
                    self.set_status("Processing", "Thinking...")
            elif event_type == "conversation.item.input_audio_transcription.completed":
                transcript = data.get("transcript", "")
                self.logger.info(f"User said: {transcript}")
                if transcript and self._command_listener:
                    try:
                        self._command_listener(transcript)
                    except Exception as e:
                        self.logger.debug(f"Command listener error: {e}")
            elif event_type == "response.output_audio.delta":
                audio_data = base64.b64decode(data.get("delta", ""))
                if audio_data:
                    self._response_audio_bytes += len(audio_data)
                    self._playback_queue.put(audio_data)
            elif event_type == "response.output_audio_transcript.delta":
                pass  # spoken text mirror; not displayed currently
            elif event_type == "response.output_text.delta":
                pass
            elif event_type == "response.done":
                self._on_response_done(data)
            elif event_type == "error":
                err = data.get("error", {})
                self.logger.error(f"Realtime API error: {err}")
                api_tracker.failure("ai_voice", "openai-realtime")
        except Exception as e:
            self.logger.error(f"Error processing WebSocket message: {e}", exc_info=True)

    def _on_response_done(self, data):
        status = data.get("response", {}).get("status")
        self.logger.info(f"Response completed: status={status}")
        self._last_voice_activity = time.time()
        if status == "failed":
            api_tracker.failure("ai_voice", "openai-realtime")
            self.retry_count += 1
            if self.retry_count <= 3 and not self.live_mic:
                self.logger.warning(
                    f"Response failed, retrying (attempt {self.retry_count}/3)"
                )
                threading.Thread(
                    target=self._retry_response_create, daemon=True
                ).start()
            else:
                self.retry_count = 0
                self.set_status("Error", "Response failed")
        else:
            self.retry_count = 0
            # Estimate cost from the actual response audio length so the
            # api_tracker daily cost ceiling tracks real usage
            out_seconds = self._response_audio_bytes / 2 / self.sample_rate
            cost = max(MIN_RESPONSE_COST, out_seconds * EST_COST_PER_RESPONSE_SECOND)
            api_tracker.record("ai_voice", "openai-realtime", estimated_cost=cost)
            # If this response used up the budget, end the conversation
            # now instead of letting the next turn fail mid-sentence
            if self.conversation_active and not api_tracker.allow("ai_voice", "openai-realtime"):
                self.stop_conversation(reason="rate/cost limit reached")
                self.set_status("Ready", "Voice limit reached for now")
            # Playback thread flips status back when its queue drains
        self._response_audio_bytes = 0

    def _retry_response_create(self):
        time.sleep(2 * self.retry_count)
        self.send_ws_message({
            "type": "response.create",
            "response": {"output_modalities": ["audio"]},
        })
        self.set_status("Processing", f"Retrying (attempt {self.retry_count}/3)...")

    def _write_debug_event(self, event_type, data):
        try:
            os.makedirs(_DEBUG_DIR, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            debug_file = os.path.join(
                _DEBUG_DIR, f"ws_{timestamp}_{event_type.replace('.', '_')}.json"
            )
            with open(debug_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def on_ws_error(self, ws, error):
        self.logger.error(f"WebSocket error: {error}")
        self.session_ready = False
        api_tracker.failure("ai_voice", "openai-realtime")
        if not self.reconnecting:
            threading.Thread(target=self.reconnect_websocket, daemon=True).start()

    def on_ws_close(self, ws, close_status_code, close_msg):
        self.logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.session_ready = False
        if self.running and not self.reconnecting:
            threading.Thread(target=self.reconnect_websocket, daemon=True).start()

    def _send_loop(self):
        while self.running:
            try:
                if not self.session_ready or not hasattr(self, "ws"):
                    time.sleep(0.1)
                    continue
                message = self.send_queue.get(timeout=1.0)
                self.ws.send(json.dumps(message))
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
        if not api_tracker.allow("ai_voice", "openai-realtime"):
            self.set_status("Error", "Rate limited")
            return
        self.reconnecting = True
        self.logger.info("Reconnecting WebSocket...")
        # A live conversation cannot survive a new session
        if self.conversation_active:
            self.stop_conversation(reason="connection lost")
        if hasattr(self, "ws"):
            try:
                self.ws.close()
            except Exception:
                pass
        time.sleep(2)
        self.connect_websocket_thread()
        if self.session_ready:
            self.logger.info("WebSocket reconnected successfully")
            self.set_status("Ready", "Press SPACE to talk")
        else:
            self.logger.error("Failed to reconnect WebSocket")
            self.set_status("Error", "Connection failed")
        self.reconnecting = False

    # ------------------------------------------------------------------
    # Conversation flow
    # ------------------------------------------------------------------

    def on_button_press(self):
        self.logger.info("Voice interaction triggered")
        if not self.session_ready:
            self.logger.warning("Realtime session not ready")
            self.set_status("Error", "Not connected")
            return
        if self.live_mic:
            if self.conversation_active:
                self.stop_conversation(reason="user ended")
            else:
                self.start_conversation()
        else:
            # Fallback: single test-WAV exchange per press
            if not self.recording:
                self.start_test_wav_exchange()

    def start_conversation(self):
        """Begin a hands-free conversation: stream mic, server VAD turns."""
        if not api_tracker.allow("ai_voice", "openai-realtime"):
            self.set_status("Error", "Rate limited")
            return
        self.conversation_active = True
        self.recording = True
        self._last_voice_activity = time.time()
        self._conversation_started = time.time()
        self._mute_until = 0.0
        self.send_ws_message({"type": "input_audio_buffer.clear"})
        self._mic_thread = threading.Thread(
            target=self._mic_loop, daemon=True, name="voice-mic"
        )
        self._mic_thread.start()
        self.set_status("Listening", "Just talk - SPACE to end")

    def stop_conversation(self, reason=""):
        self.logger.info(f"Ending conversation ({reason})")
        self.conversation_active = False
        self.recording = False
        self._stop_mic_proc()
        self.send_ws_message({"type": "input_audio_buffer.clear"})
        self.set_status("Ready", "Press SPACE to talk")

    def _stop_mic_proc(self):
        proc = self._mic_proc
        self._mic_proc = None
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _mic_loop(self):
        """Stream the USB mic to the API until the conversation ends.

        arecord writes raw S16_LE 24 kHz mono PCM to stdout; plughw lets
        ALSA do the resampling from whatever the mic natively supports.
        Chunks are dropped while the mirror is speaking (echo gate).
        """
        cmd = [
            "arecord", "-q", "-t", "raw",
            "-f", "S16_LE", "-r", str(self.sample_rate),
            "-c", str(self.channels), "-D", self.capture_device,
        ]
        self.logger.info(f"Starting mic capture: {' '.join(cmd)}")
        try:
            self._mic_proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
        except Exception as e:
            self.logger.error(f"Failed to start arecord: {e}")
            self.conversation_active = False
            self.recording = False
            self.set_status("Error", "Mic capture failed")
            return

        chunk_bytes = int(self.sample_rate * MIC_CHUNK_SEC) * 2  # 16-bit mono
        end_message = "Press SPACE to talk"
        next_limit_check = time.time() + LIMIT_CHECK_EVERY_SEC
        try:
            while self.running and self.conversation_active:
                proc = self._mic_proc
                if proc is None:
                    break
                data = proc.stdout.read(chunk_bytes)
                if not data:
                    self.logger.error("arecord stream ended unexpectedly")
                    break

                now = time.time()

                # Idle timeout: nobody has spoken for a while
                if now - self._last_voice_activity > self.conversation_timeout:
                    self.logger.info("Conversation idle timeout")
                    break

                # Hard cap: no conversation runs forever, active or not
                if now - self._conversation_started > self.max_conversation_sec:
                    self.logger.info(
                        f"Conversation hard cap reached "
                        f"({self.max_conversation_sec}s)"
                    )
                    end_message = "Time limit - SPACE to talk again"
                    break

                # Periodic budget check while the conversation runs
                if now >= next_limit_check:
                    next_limit_check = now + LIMIT_CHECK_EVERY_SEC
                    if not api_tracker.allow("ai_voice", "openai-realtime"):
                        self.logger.warning(
                            "Voice rate/cost limit hit mid-conversation"
                        )
                        end_message = "Voice limit reached for now"
                        break

                # Echo gate: do not send the mirror's own voice back
                if self._playback_active or now < self._mute_until:
                    continue

                self.send_ws_message({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(data).decode("utf-8"),
                })
        except Exception as e:
            self.logger.error(f"Mic loop error: {e}", exc_info=True)
        finally:
            ended_by_loop = self.conversation_active
            self._stop_mic_proc()
            if ended_by_loop:
                # Timeout, cap, limit, or capture failure: close out cleanly
                self.conversation_active = False
                self.recording = False
                self.set_status("Ready", end_message)

    # ------------------------------------------------------------------
    # Test-WAV fallback (no microphone available)
    # ------------------------------------------------------------------

    def start_test_wav_exchange(self):
        self.recording = True
        self.retry_count = 0
        self.set_status("Listening", "Streaming test audio...")
        self.audio_thread = threading.Thread(
            target=self._stream_test_wav, daemon=True, name="voice-stream"
        )
        self.audio_thread.start()

    def _stream_test_wav(self):
        """Stream the pre-recorded test WAV with manual commit."""
        try:
            test_audio_path = os.path.join(_DATA_DIR, "test_spedup.wav")
            if not os.path.exists(test_audio_path):
                self.logger.error(f"Test audio file not found: {test_audio_path}")
                self.set_status("Error", "No test audio file")
                return

            with open(test_audio_path, "rb") as f:
                pcm_data = f.read()

            if len(pcm_data) <= 4800:
                self.logger.warning("Test audio too short, skipping")
                return

            self.send_ws_message({"type": "input_audio_buffer.clear"})
            chunk_size = 16000
            for i in range(0, len(pcm_data), chunk_size):
                chunk = pcm_data[i:i + chunk_size]
                self.send_ws_message({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(chunk).decode("utf-8"),
                })

            self.send_ws_message({"type": "input_audio_buffer.commit"})
            self.send_ws_message({
                "type": "response.create",
                "response": {"output_modalities": ["audio"]},
            })
            self.set_status("Processing", "Waiting for AI response...")
        except Exception as e:
            self.logger.error(f"Streaming error: {e}", exc_info=True)
            self.set_status("Error", f"Streaming failed: {str(e)[:40]}")
        finally:
            self.recording = False

    # ------------------------------------------------------------------
    # Playback (gapless, with avatar lipsync feed and mic echo gate)
    # ------------------------------------------------------------------

    def _playback_loop(self):
        """Feed PCM chunks to a pygame channel back-to-back.

        Runs in its own thread so the WebSocket reader is never blocked
        by audio playback. Sets _playback_active so the mic loop gates
        itself while the mirror speaks, and forwards each chunk to the
        avatar audio sink for lipsync.
        """
        channel = None
        while self.running:
            try:
                chunk = self._playback_queue.get(timeout=0.5)
            except Empty:
                if self._playback_active and (channel is None or not channel.get_busy()):
                    self._playback_active = False
                    self._mute_until = time.time() + UNMUTE_TAIL_SEC
                    self._last_voice_activity = time.time()
                    if self.conversation_active:
                        self.set_status("Listening", "Just talk - SPACE to end")
                    else:
                        self.set_status("Ready", "Press SPACE to talk")
                continue

            try:
                if len(chunk) < 4:
                    continue
                if not pygame.mixer.get_init():
                    pygame.mixer.init(
                        frequency=self.sample_rate, size=-16, channels=1
                    )

                if not self._playback_active:
                    self._playback_active = True
                    self.set_status("Speaking", "Playing response...")

                if self._audio_sink:
                    try:
                        self._audio_sink(chunk)
                    except Exception as e:
                        self.logger.debug(f"Avatar audio sink error: {e}")

                sound = pygame.mixer.Sound(buffer=chunk)
                if channel is None or not channel.get_busy():
                    channel = sound.play()
                else:
                    # Wait for the queue slot, then chain for gapless output
                    while channel.get_queued() and self.running:
                        time.sleep(0.005)
                    channel.queue(sound)
            except Exception as e:
                self.logger.error(f"Playback error: {e}")

    # ------------------------------------------------------------------
    # Status / drawing / cleanup
    # ------------------------------------------------------------------

    def set_status(self, status, message):
        self.status = status
        self.status_message = message
        self.logger.info(f"Status: {status} - {message}")
        if self._state_listener:
            try:
                self._state_listener(status)
            except Exception as e:
                self.logger.debug(f"State listener error: {e}")

    def update(self):
        pass

    def draw(self, screen, position):
        """Draw voice AI status -- only visible when active. No background."""
        try:
            if isinstance(position, dict):
                x, y = position.get("x", 0), position.get("y", 0)
                width = position.get("width", 300)
            else:
                x, y = position
                width = 300

            # Only draw when actively doing something
            if not self.recording and self.status in ("Ready", "idle", "disconnected", ""):
                return

            if not hasattr(self, "_voice_font_ready") or not self._voice_font_ready:
                from config import FONT_NAME, FONT_SIZE_BODY, FONT_SIZE_SMALL
                self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE_SMALL)
                self.title_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE_BODY)
                self._voice_font_ready = True

            center_x = x + width // 2

            title = self.title_font.render(f"Voice: {self.status}", True, (150, 150, 255))
            title.set_alpha(200)
            screen.blit(title, (center_x - title.get_width() // 2, y))

            if self.status_message:
                msg = self.status_message[:40] + "..." if len(self.status_message) > 40 else self.status_message
                msg_surf = self.font.render(msg, True, (160, 160, 160))
                msg_surf.set_alpha(200)
                screen.blit(msg_surf, (center_x - msg_surf.get_width() // 2, y + 28))

            if self.conversation_active:
                pulse = int(128 + 127 * (pygame.time.get_ticks() % 1000) / 1000)
                live_color = (pulse, 255, pulse) if not self._playback_active else (160, 160, 160)
                pygame.draw.circle(screen, live_color, (center_x - 30, y + 55), 6)
                live_text = self.font.render("Live", True, live_color)
                screen.blit(live_text, (center_x - 18, y + 47))
        except Exception as e:
            self.logger.error(f"Draw error: {e}")

    def cleanup(self):
        self.running = False
        self.conversation_active = False
        self._stop_mic_proc()
        if hasattr(self, "ws"):
            try:
                self.ws.close()
            except Exception:
                pass
        for attr in ("audio_thread", "_mic_thread", "ws_thread_send", "_playback_thread"):
            t = getattr(self, attr, None)
            if t is not None and t.is_alive():
                t.join(timeout=2)
        if pygame.mixer.get_init():
            pygame.mixer.quit()
        self.logger.info("Cleanup complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    pygame.init()
    screen = pygame.display.set_mode((800, 480))
    module = AIVoiceModule({"openai": {}})
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
