"""Cached Princess MP4 player for the centre overlay (Phase 4)."""
from __future__ import annotations
import subprocess, shutil, time
from pathlib import Path

class PrincessPlayer:
    def __init__(self, linger_seconds: float = 0.5):
        self.linger_seconds = linger_seconds; self.process = None; self.audio = None; self.audio_decoder = None
        self.surface = None; self.width = self.height = 0; self.ends_at = 0.0

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
        aplay = shutil.which("aplay")
        if aplay:
            audio_command = [aplay, "-q"]
            speaker = __import__("os").getenv("VOICE_SPEAKER", "").strip()
            if speaker: audio_command.extend(["-D", speaker])
            self.audio_decoder = subprocess.Popen([ffmpeg, "-re", "-loglevel", "error", "-i", source, "-vn", "-f", "wav", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.audio = subprocess.Popen(audio_command, stdin=self.audio_decoder.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.audio_decoder.stdout.close()
        self.ends_at = 0.0

    def update(self, pygame_module):
        if not self.process or not self.process.stdout: return
        frame = self.process.stdout.read(self.width * self.height * 3)
        if len(frame) == self.width * self.height * 3:
            self.surface = pygame_module.image.frombuffer(frame, (self.width, self.height), "RGB").copy()
        else:
            self._finish()

    def draw(self, screen, position):
        if self.surface is not None:
            screen.blit(self.surface, (position.get("x", 0), position.get("y", 0)))

    def stop(self):
        for process in (self.process, self.audio, self.audio_decoder):
            if process and process.poll() is None: process.terminate()
        self.process = self.audio = self.audio_decoder = None; self.surface = None

    def _finish(self):
        """Release decoder/audio processes but keep the last video frame visible."""
        for process in (self.process, self.audio, self.audio_decoder):
            if process and process.poll() is None: process.terminate()
        self.process = self.audio = self.audio_decoder = None

    def cleanup(self): self.stop()
