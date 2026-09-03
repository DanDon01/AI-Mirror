"""Cached Princess MP4 player for the centre overlay (Phase 4)."""
from __future__ import annotations
import subprocess, shutil, time
from pathlib import Path

class PrincessPlayer:
    def __init__(self, linger_seconds: float = 0.5):
        self.linger_seconds = linger_seconds; self.process = None; self.audio = None
        self.surface = None; self.width = self.height = 0; self.ends_at = 0.0

    @property
    def playing(self): return self.process is not None

    def play(self, path: str | Path, size: tuple[int, int]):
        self.stop(); self.width, self.height = map(int, size); source = str(Path(path).resolve())
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg: raise RuntimeError("ffmpeg is required for Princess playback")
        self.process = subprocess.Popen([ffmpeg, "-loglevel", "error", "-i", source,
            "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:color=black",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        ffplay = shutil.which("ffplay")
        if ffplay: self.audio = subprocess.Popen([ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", source], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ends_at = 0.0

    def update(self, pygame_module):
        if not self.process or not self.process.stdout: return
        frame = self.process.stdout.read(self.width * self.height * 3)
        if len(frame) == self.width * self.height * 3:
            self.surface = pygame_module.image.frombuffer(frame, (self.width, self.height), "RGB").copy()
        else:
            self.stop()

    def draw(self, screen, position):
        if self.surface is not None:
            screen.blit(self.surface, (position.get("x", 0), position.get("y", 0)))

    def stop(self):
        for process in (self.process, self.audio):
            if process and process.poll() is None: process.terminate()
        self.process = self.audio = None; self.surface = None

    def cleanup(self): self.stop()
