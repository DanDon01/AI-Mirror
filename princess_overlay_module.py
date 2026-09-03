"""Opt-in centre overlay for playing an approved cached Princess clip."""
from __future__ import annotations
import pygame
from princess_player import PrincessPlayer

class PrincessOverlayModule:
    def __init__(self, size=420, **kwargs):
        self.player = PrincessPlayer(); self.size = int(size)
    def play_cached(self, path, position=None):
        position = position or {}
        self.player.play(path, (max(1, int(position.get("width", self.size))), max(1, int(position.get("height", self.size)))))
    def update(self): self.player.update(pygame)
    def draw(self, screen, position): self.player.draw(screen, position)
    def cleanup(self): self.player.cleanup()
