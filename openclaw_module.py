"""OpenClaw integration module for AI-Mirror.

Connects to an OpenClaw Gateway running on a separate Linux system
over the local network via WebSocket. Displays incoming messages,
provides voice reply routing, and shows a multi-channel inbox.

The Gateway is NOT installed on the Pi or the dev machine -- it runs
on a dedicated Linux system and the mirror connects to it remotely.
"""

import pygame
import logging
import os
import json
import time as time_module
import threading
import uuid
from datetime import datetime
from config import (
    CONFIG, FONT_NAME, COLOR_FONT_DEFAULT, COLOR_FONT_TITLE,
    COLOR_FONT_BODY, COLOR_FONT_SMALL, COLOR_BG_MODULE_ALPHA,
    COLOR_BG_HEADER_ALPHA, TRANSPARENCY,
)
from visual_effects import VisualEffects
from config import draw_module_background_fallback

logger = logging.getLogger("OpenClaw")

# Channel display colours
CHANNEL_COLORS = {
    "whatsapp": (37, 211, 102),
    "telegram": (0, 136, 204),
    "slack": (97, 31, 105),
    "discord": (88, 101, 242),
    "signal": (59, 118, 195),
    "imessage": (52, 199, 89),
    "teams": (70, 70, 230),
    "email": (180, 180, 180),
}

CHANNEL_LABELS = {
    "whatsapp": "WA",
    "telegram": "TG",
    "slack": "SL",
    "discord": "DC",
    "signal": "SG",
    "imessage": "iM",
    "teams": "TM",
    "email": "EM",
}


class OpenClawModule:
    """OpenClaw Gateway client for the AI-Mirror.

    Connects to a remote OpenClaw Gateway via WebSocket, receives
    incoming messages as notifications, and displays a multi-channel inbox.
    """

    def __init__(self, gateway_url=None, token=None, device_id="ai-mirror-pi5",
                 notification_timeout=10, max_inbox_messages=5,
                 channels_display=None, voice_reply_enabled=True, **kwargs):
        """
        Args:
            gateway_url: WebSocket URL of the remote OpenClaw Gateway
                         (e.g. 'ws://192.168.1.100:18789')
            token: authentication token for the Gateway
            device_id: unique device identifier for this mirror
            notification_timeout: seconds before notifications auto-dismiss
            max_inbox_messages: max messages shown in inbox view
            channels_display: list of channel names to show (None = all)
            voice_reply_enabled: whether voice replies are supported
        """
        self.gateway_url = gateway_url or os.getenv("OPENCLAW_GATEWAY_URL", "")
        self.token = token or os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
        self.device_id = device_id
        self.notification_timeout = notification_timeout
        self.max_inbox = max_inbox_messages
        self.channels_display = channels_display
        self.voice_reply_enabled = voice_reply_enabled

        self.effects = VisualEffects()
        self.ws = None
        self.connected = False
        self.connect_error = None
        self.notifications = []  # Active notification overlays
        self.inbox = []  # Recent messages
        self._ws_thread = None
        self._lock = threading.Lock()

        self.title_font = None
        self.body_font = None
        self.small_font = None
        self.channel_font = None

        if self.gateway_url and self.token:
            self._start_connection()
        else:
            self.connect_error = "No gateway URL or token configured"
            logger.warning(self.connect_error)

    def _init_fonts(self):
        if self.title_font is None:
            styling = CONFIG.get("module_styling", {})
            fonts = styling.get("fonts", {})
            title_size = fonts.get("title", {}).get("size", 18)
            body_size = fonts.get("body", {}).get("size", 14)
            small_size = fonts.get("small", {}).get("size", 12)
            self.title_font = pygame.font.SysFont(FONT_NAME, title_size)
            self.body_font = pygame.font.SysFont(FONT_NAME, body_size)
            self.small_font = pygame.font.SysFont(FONT_NAME, small_size)
            self.channel_font = pygame.font.SysFont(FONT_NAME, small_size, bold=True)

    def _start_connection(self):
        """Start WebSocket connection in a background thread."""
        self._ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self._ws_thread.start()

    def _ws_loop(self):
        """WebSocket connection loop with auto-reconnect."""
        try:
            import websocket
        except ImportError:
            self.connect_error = "websocket-client not installed"
            logger.error(self.connect_error)
            return

        retry_delay = 5
        max_retry = 300  # 5 minutes max

        while True:
            try:
                logger.info(f"Connecting to OpenClaw Gateway at {self.gateway_url}")
                self.ws = websocket.WebSocketApp(
                    self.gateway_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self.ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

            self.connected = False
            logger.info(f"Reconnecting in {retry_delay}s...")
            time_module.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry)

    def _on_open(self, ws):
        """Send connection handshake."""
        logger.info("WebSocket connected, sending handshake")
        handshake = {
            "type": "req",
            "id": str(uuid.uuid4()),
            "method": "connect",
            "params": {
                "minProtocol": 3,
                "maxProtocol": 3,
                "client": {
                    "id": "ai-mirror",
                    "version": "1.0.0",
                    "platform": "linux",
                    "mode": "node",
                },
                "role": "node",
                "caps": ["screen", "voice", "notifications"],
                "commands": [
                    "screen.display",
                    "voice.speak",
                    "voice.listen",
                    "notifications.show",
                ],
                "auth": {"token": self.token},
                "device": {"id": self.device_id},
            },
        }
        ws.send(json.dumps(handshake))

    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "hello-ok":
                self.connected = True
                self.connect_error = None
                logger.info("OpenClaw Gateway handshake complete")

            elif msg_type == "event":
                self._handle_event(data)

            elif msg_type == "error":
                error_msg = data.get("error", {}).get("message", "Unknown error")
                logger.error(f"Gateway error: {error_msg}")
                self.connect_error = error_msg

        except json.JSONDecodeError:
            logger.warning("Received non-JSON message from Gateway")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _on_error(self, ws, error):
        self.connect_error = str(error)
        logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self.connected = False
        logger.info(f"WebSocket closed: {close_status_code} {close_msg}")

    def _handle_event(self, data):
        """Process an incoming event from the Gateway."""
        event_name = data.get("event", "")
        payload = data.get("data", {})

        if event_name == "message":
            sender = payload.get("sender", "Unknown")
            channel = payload.get("channel", "unknown").lower()
            text = payload.get("text", "")
            timestamp = datetime.now()

            # Filter by configured channels
            if self.channels_display and channel not in self.channels_display:
                return

            msg = {
                "sender": sender,
                "channel": channel,
                "text": text,
                "timestamp": timestamp,
                "read": False,
            }

            with self._lock:
                # Add to notifications
                self.notifications.append(msg)

                # Add to inbox
                self.inbox.insert(0, msg)
                self.inbox = self.inbox[:self.max_inbox]

            logger.info(f"Message from {sender} via {channel}: {text[:50]}")

    def send_reply(self, channel, recipient, text):
        """Send a reply through the Gateway back to the originating channel."""
        if not self.connected or not self.ws:
            logger.warning("Cannot send reply: not connected to Gateway")
            return False

        reply = {
            "type": "req",
            "id": str(uuid.uuid4()),
            "method": "message.send",
            "params": {
                "channel": channel,
                "recipient": recipient,
                "text": text,
            },
        }
        try:
            self.ws.send(json.dumps(reply))
            logger.info(f"Reply sent to {recipient} via {channel}: {text[:50]}")
            return True
        except Exception as e:
            logger.error(f"Failed to send reply: {e}")
            return False

    def dismiss_notifications(self):
        """Clear all active notifications."""
        with self._lock:
            self.notifications.clear()

    def update(self):
        # Auto-dismiss expired notifications
        now = datetime.now()
        with self._lock:
            self.notifications = [
                n for n in self.notifications
                if (now - n["timestamp"]).total_seconds() < self.notification_timeout
            ]

    def draw(self, screen, position):
        try:
            if isinstance(position, dict):
                x, y = position["x"], position["y"]
                width = position.get("width", 225)
                height = position.get("height", 200)
            else:
                x, y = position
                width, height = 225, 200

            self._init_fonts()

            styling = CONFIG.get("module_styling", {})
            radius = styling.get("radius", 15)
            padding = styling.get("spacing", {}).get("padding", 10)

            # Background
            module_rect = pygame.Rect(x - padding, y - padding, width, height)
            header_rect = pygame.Rect(x - padding, y - padding, width, 40)
            try:
                self.effects.draw_rounded_rect(screen, module_rect, COLOR_BG_MODULE_ALPHA, radius=radius, alpha=0)
                self.effects.draw_rounded_rect(screen, header_rect, COLOR_BG_HEADER_ALPHA, radius=radius, alpha=0)
            except Exception:
                draw_module_background_fallback(screen, x, y, width, height, padding)

            # Title with connection status
            status_color = (100, 255, 100) if self.connected else (255, 100, 100)
            title_surf = self.title_font.render("OpenClaw", True, COLOR_FONT_TITLE)
            screen.blit(title_surf, (x + padding, y + padding))

            # Connection indicator dot
            dot_x = x + padding + title_surf.get_width() + 8
            dot_y = y + padding + title_surf.get_height() // 2
            pygame.draw.circle(screen, status_color, (dot_x, dot_y), 4)

            draw_y = y + 50

            # Connection error
            if self.connect_error and not self.connected:
                err_text = self.connect_error[:30]
                err_surf = self.small_font.render(err_text, True, (255, 162, 173))
                err_surf.set_alpha(TRANSPARENCY)
                screen.blit(err_surf, (x, draw_y))
                draw_y += 20

            # Inbox
            with self._lock:
                inbox_copy = list(self.inbox)

            if not inbox_copy and self.connected:
                empty = self.body_font.render("No messages", True, COLOR_FONT_SMALL)
                empty.set_alpha(TRANSPARENCY)
                screen.blit(empty, (x, draw_y))
            elif not inbox_copy and not self.connected:
                if not self.gateway_url:
                    hint = self.small_font.render("Set OPENCLAW_GATEWAY_URL", True, COLOR_FONT_SMALL)
                else:
                    hint = self.small_font.render("Connecting...", True, COLOR_FONT_SMALL)
                hint.set_alpha(TRANSPARENCY)
                screen.blit(hint, (x, draw_y))
            else:
                for msg in inbox_copy[:4]:
                    channel = msg["channel"]
                    ch_color = CHANNEL_COLORS.get(channel, (150, 150, 150))
                    ch_label = CHANNEL_LABELS.get(channel, channel[:2].upper())

                    # Channel badge
                    badge_surf = self.channel_font.render(f"[{ch_label}]", True, ch_color)
                    screen.blit(badge_surf, (x, draw_y))

                    # Sender
                    sender_surf = self.small_font.render(msg["sender"], True, COLOR_FONT_BODY)
                    sender_surf.set_alpha(TRANSPARENCY)
                    screen.blit(sender_surf, (x + badge_surf.get_width() + 5, draw_y))

                    # Time ago
                    ago = (datetime.now() - msg["timestamp"]).total_seconds()
                    if ago < 60:
                        time_str = "now"
                    elif ago < 3600:
                        time_str = f"{int(ago // 60)}m"
                    else:
                        time_str = f"{int(ago // 3600)}h"
                    time_surf = self.small_font.render(time_str, True, COLOR_FONT_SMALL)
                    screen.blit(time_surf, (x + width - padding * 2 - time_surf.get_width(), draw_y))

                    draw_y += 16

                    # Message preview (truncated)
                    preview = msg["text"][:35]
                    if len(msg["text"]) > 35:
                        preview += "..."
                    preview_surf = self.small_font.render(preview, True, COLOR_FONT_SMALL)
                    preview_surf.set_alpha(TRANSPARENCY)
                    screen.blit(preview_surf, (x + 5, draw_y))

                    draw_y += 22

        except Exception as e:
            logger.error(f"Error drawing OpenClaw module: {e}")

    def cleanup(self):
        """Close WebSocket connection."""
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        self.connected = False
