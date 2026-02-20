# AI-Mirror: OpenClaw Integration Design

## What is OpenClaw?

[OpenClaw](https://openclaw.ai/) is a self-hosted personal AI assistant platform. Key features:

- **Multi-channel:** WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, Teams
- **Local-first Gateway:** WebSocket-based communication hub running on your own infrastructure
- **Tools:** Browser, canvas, cron, multi-channel inbox
- **Self-hosted:** Runs on your own devices/servers, data stays local

## Why Integrate?

The AI-Mirror becomes another "channel" in the OpenClaw ecosystem:
- See incoming messages from all platforms on the mirror
- Reply via voice (speak to the mirror, message sent via WhatsApp/Telegram/etc.)
- Use OpenClaw's AI agent (with persistent memory and tools) instead of raw GPT-4o
- Receive scheduled notifications (morning briefing, reminders) via OpenClaw's cron tool
- The mirror acts as a household communication hub

## Architecture

```
+-------------------+     WebSocket     +-------------------+
|   AI-Mirror       | <--------------> |  OpenClaw Gateway  |
|   (Node Client)   |   JSON frames     |  (localhost:18789) |
|                   |                   |                   |
|  Capabilities:    |                   |  Connected to:    |
|  - screen.display |                   |  - WhatsApp       |
|  - voice.input    |                   |  - Telegram       |
|  - voice.output   |                   |  - Slack          |
|  - notifications  |                   |  - Discord        |
+-------------------+                   |  - Signal         |
                                        |  - iMessage       |
                                        +-------------------+
```

The mirror connects to the OpenClaw Gateway as a **Node** role client. It declares capabilities (screen, voice, notifications) and receives dispatched events.

## Module Design: `openclaw_module.py`

Standard module interface: `__init__`, `update`, `draw`, `cleanup`.

### Connection

Uses `websocket-client` (already in requirements.txt) to maintain a persistent WebSocket connection to the Gateway.

```python
class OpenClawModule:
    def __init__(self, gateway_url, token, device_id, **kwargs):
        self.gateway_url = gateway_url  # ws://localhost:18789
        self.token = token
        self.device_id = device_id
        self.notification_timeout = kwargs.get('notification_timeout', 10)
        self.max_inbox = kwargs.get('max_inbox_messages', 5)
        self.channels_display = kwargs.get('channels_display', [])
        self.voice_reply_enabled = kwargs.get('voice_reply_enabled', True)

        self.ws = None
        self.connected = False
        self.notifications = []  # Active notification queue
        self.inbox = []  # Recent messages
        self._connect()
```

### Handshake

On connection, send a `connect` request declaring the mirror as a node:

```python
connect_message = {
    "type": "req",
    "id": generate_uuid(),
    "method": "connect",
    "params": {
        "minProtocol": 3,
        "maxProtocol": 3,
        "client": {
            "id": "ai-mirror",
            "version": "1.0.0",
            "platform": "linux",
            "mode": "node"
        },
        "role": "node",
        "caps": ["screen", "voice", "notifications"],
        "commands": [
            "screen.display",
            "voice.speak",
            "voice.listen",
            "notifications.show"
        ],
        "auth": {
            "token": self.token
        },
        "device": {
            "id": self.device_id
        }
    }
}
```

### Incoming Messages

When a message arrives on any channel, the Gateway dispatches it to the mirror node. The module renders it as a notification overlay:

```
+------------------------------------------+
| [WhatsApp] Dan                     2m ago |
| Hey, are you home?                        |
+------------------------------------------+
```

Features:
- Sender name, channel icon (colour-coded), message preview
- Auto-dismiss after configurable timeout (default 10 seconds)
- Queue for multiple messages with count badge
- Voice command: "dismiss" to clear

### Voice Reply

User says: "Reply to Dan: I'll be home in 10 minutes"

Flow:
1. Existing voice pipeline captures speech
2. `voice_commands.py` extended with reply pattern matching
3. Module sends reply as a node command response to the Gateway
4. Gateway routes it back through the originating channel (e.g., WhatsApp)

### Multi-Channel Inbox

Dedicated display area showing last 5 messages across all channels:

```
+------------------------------------------+
|  Inbox (3 messages)                       |
|                                           |
|  [WA] Dan: Hey, are you home?      2m    |
|  [TG] Work Group: Meeting at 3pm   15m   |
|  [SL] #general: Build deployed      1h   |
+------------------------------------------+
```

Colour coding:
- WhatsApp: green
- Telegram: blue
- Slack: purple
- Discord: indigo
- Signal: dark blue
- iMessage: light blue

Voice command: "Read messages" triggers TTS readout of unread messages.

### AI Agent Relay

Instead of sending voice queries directly to GPT-4o, route them through OpenClaw's agent runtime:

Benefits:
- Persistent memory across sessions and channels
- Access to OpenClaw tools (browser, calendar, cron)
- Multi-session context (conversation started on phone can continue on mirror)
- Unified AI personality across all channels

Flow:
1. User speaks to mirror
2. Mirror sends query to OpenClaw Gateway as agent request
3. OpenClaw's agent processes with full context
4. Response returned to mirror for TTS playback

### Cron Integration

OpenClaw's cron tool can schedule messages to the mirror node:
- Morning briefing at 7:00 AM (weather, calendar, commute)
- Medication reminders
- Appointment alerts
- Custom scheduled messages

## Implementation Phases

### Phase 1: Connection (Low effort)
- WebSocket connection to Gateway
- Challenge/response handshake
- Heartbeat maintenance (tick interval from `hello-ok` response)
- Connection status display in module

### Phase 2: Notifications (Medium effort)
- Subscribe to message events
- Render notification overlays
- Notification queue with auto-dismiss
- "dismiss" voice command

### Phase 3: Voice Reply (Medium effort)
- Extend voice_commands.py with reply patterns
- Capture and route voice replies through Gateway
- Confirmation display after sending

### Phase 4: Inbox Display (Medium effort)
- Persistent message list
- Channel icons and colour coding
- Voice-triggered TTS readout
- Read/unread tracking

### Phase 5: Agent Relay (High effort)
- Route AI queries through OpenClaw agent
- Handle streaming responses
- Session management
- Fallback to direct GPT-4o if Gateway unavailable

## Configuration

### config.py addition

```python
'openclaw': {
    'class': 'OpenClawModule',
    'params': {
        'gateway_url': 'ws://localhost:18789',
        'token': os.getenv('OPENCLAW_GATEWAY_TOKEN'),
        'device_id': 'ai-mirror-pi5',
        'notification_timeout': 10,
        'max_inbox_messages': 5,
        'channels_display': ['whatsapp', 'telegram', 'slack'],
        'voice_reply_enabled': True,
    }
}
```

### Environment variable

Add to `Variables.env`:
```
OPENCLAW_GATEWAY_TOKEN=your-gateway-token
```

### Module visibility

Add to `module_visibility`:
```python
'openclaw': True
```

## Dependencies

- `websocket-client` -- already in requirements.txt
- No additional packages needed

## Prerequisites

1. OpenClaw Gateway running (self-hosted, see [docs](https://docs.openclaw.ai/gateway))
2. At least one channel connected (WhatsApp, Telegram, etc.)
3. Gateway token generated for the mirror node
4. Network connectivity between Pi and Gateway host (can be same machine or LAN)

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Gateway offline | Fall back to direct GPT-4o for AI queries. Show "OpenClaw disconnected" status. |
| WebSocket drops | Auto-reconnect with exponential backoff (3 retries, then 5-min cooldown). |
| Message flood | Rate limit notification display (max 1 per 3 seconds). Queue excess. |
| Privacy | All data stays local (self-hosted Gateway). No cloud dependency. |
| Latency | WebSocket is low-latency. Agent relay may add 1-2s for complex queries. |
