"""Cached Princess MP4 player for the centre overlay (Phase 4)."""
from __future__ import annotations
import subprocess, shutil, threading, time
from pathlib import Path
from queue import Empty, Queue

class PrincessPlayer:
    def __init__(self, linger_seconds: float = 0.5):
        self.linger_seconds = linger_seconds; self.process = None; self.audio = None; self.audio_decoder = None
        self.surface = None; self.width = self.height = 0; self.ends_at = 0.0
        self._frames = Queue()

    @property
    def playing(self): return self.process is not None

    @property
    def has_frame(self): return self.surface is not None

    def play(self, path: str | Path, size: tuple[int, int]):
        self.stop(); self.width, self.height = map(int, size)
        raw_source = str(path)
        source = raw_source if raw_source.startswith(("https://", "http://")) else str(Path(path).resolve())
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg: raise RuntimeError("ffmpeg is required for Princess playback")
        self.process = subprocess.Popen([ffmpeg, "-re", "-loglevel", "error", "-i", source,
            "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:color=black",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._frames = Queue()
        threading.Thread(target=self._decode_frames, args=(self.process, self.width, self.height, self._frames), daemon=True, name="princess-video-decode").start()
        aplay = shutil.which("aplay")
        if aplay:
            audio_command = [aplay, "-q"]
            speaker = __import__("os").getenv("VOICE_SPEAKER", "").strip()
            if speaker: audio_command.extend(["-D", speaker])
            self.audio_decoder = subprocess.Popen([ffmpeg, "-re", "-loglevel", "error", "-i", source, "-vn", "-f", "wav", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.audio = subprocess.Popen(audio_command, stdin=self.audio_decoder.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.audio_decoder.stdout.close()
        self.ends_at = 0.0

    @staticmethod
    def _decode_frames(process, width, height, frames):
        """Keep blocking ffmpeg pipe reads away from the Pygame/UI thread."""
        frame_bytes = width * height * 3
        try:
            while process.stdout:
                frame = process.stdout.read(frame_bytes)
                if len(frame) != frame_bytes:
                    break
                frames.put(frame)
        finally:
            frames.put(None)

    def update(self, pygame_module):
        if not self.process: return
        last_frame = None; finished = False
        while True:
            try:
                frame = self._frames.get_nowait()
            except Empty:
                break
            if frame is None:
                finished = True
            else:
                last_frame = frame
        if last_frame is not None:
            self.surface = pygame_module.image.frombuffer(last_frame, (self.width, self.height), "RGB").copy()
        if finished:
            self._finish()

    def draw(self, screen, position):
        if self.surface is not None:
            screen.blit(self.surface, (position.get("x", 0), position.get("y", 0)))

    def stop(self):
        for process in (self.process, self.audio, self.audio_decoder):
            if process and process.poll() is None: process.terminate()
        self.process = self.audio = self.audio_decoder = None; self.surface = None; self._frames = Queue()

    def _finish(self):
        """Release decoder/audio processes but keep the last video frame visible."""
        for process in (self.process, self.audio, self.audio_decoder):
            if process and process.poll() is None: process.terminate()
        self.process = self.audio = self.audio_decoder = None

    def cleanup(self): self.stop()
