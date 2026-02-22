# AI-Mirror

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.x-green.svg)
![Status](https://img.shields.io/badge/status-in%20development-yellow)
[![Made with RPi](https://img.shields.io/badge/Made%20with-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org)

> Transform any monitor into an interactive AI-powered smart mirror! Built on a Raspberry Pi 5 behind a portrait display with two-way mirror acrylic, featuring a sleek zone-based UI where content floats on the edges of a pure black background -- black is transparent through the mirror glass, leaving the center clear for your reflection.

## Screenshots

```
+--------------------------------------------+
| << 14:32:05         Fri, Feb 22  18C Fog  |  Top bar: scrolling clock, date, weather
|--------------------------------------------|
|                                            |
| WEATHER    |                  |    MIRROR  |
| Birm, UK   |                  | Good morning|
| 5.2C Fog   |                  |  You look   |
|            |                  |  great today|
| CALENDAR   |   CENTER CLEAR  |    QUOTE   |
| Meeting 2pm|   (reflection)  | "Be yourself|
|            |                  |  everyone.." |
| COUNTDOWN  |                  |     NEWS   |
| Xmas: 306d |  [notifications]| UK headline |
|            |                  |  BBC | 1/8  |
| SMART HOME |                  |    FITBIT  |
| Lounge On  |                  | Steps: 8421|
|            |                  |   SYSINFO  |
|            |                  | CPU 42C Mem |
|--------------------------------------------|
| AAPL $182 +1.2%  TSLA $245 -0.8%  NVDA >> |  Bottom bar: scrolling stock ticker
+--------------------------------------------+
```

## Key Features

- **Mirror-Optimized UI**
  - Zone-based layout: content hugs left and right edges, center stays clear for reflection
  - Pure black background (transparent through two-way mirror glass)
  - Soft text colors tuned for mirror readability at arm's length
  - Blue module titles, cyan monospace clock, color-coded data
  - Right-column modules are right-justified for visual symmetry
  - Per-module fade transitions and center notification queue

- **15 Information Modules**
  - Scrolling clock with date and weather summary (top bar)
  - Weather with animated particle effects (clouds, rain, sun, snow, storms)
  - Stock market scrolling ticker with alerts for big movers (bottom bar)
  - Google Calendar events
  - Fitbit health data (steps, calories, sleep, heart rate) with progress bars
  - Event countdowns with voice-activated timer
  - Daily inspirational quotes (ZenQuotes API + local fallback)
  - RSS news headlines from BBC and Guardian
  - OpenClaw multi-channel messaging inbox (WebSocket)
  - Home Assistant smart home entity states (auto-discover or manual config)
  - System stats: CPU temperature, memory, disk, uptime (color-coded)
  - Time-based greetings with rotating affirmations
  - Retro character screensaver (27 pop culture icons)

- **AI Voice Interaction**
  - Triple AI system with automatic fallback chain
  - ElevenLabs premium text-to-speech (eleven_multilingual_v2)
  - OpenAI Realtime API via WebSocket (gpt-4o-realtime-preview)
  - GPT-4o + OpenAI TTS with gTTS fallback
  - Voice command parsing for module control ("show weather", "hide stocks")

- **Application States**
  - **Active:** All enabled modules visible, voice ready, weather animations
  - **Screensaver:** Retro character animation with clock
  - **Sleep:** Clock only (minimal display)
  - Smooth fade transitions between states

- **Module Toggle System**
  - Keyboard shortcuts (1-0) to show/hide individual modules
  - On-screen toast notifications for toggle feedback
  - Foundation for voice-activated module control

## Hardware Requirements

- Raspberry Pi 5 (8GB RAM recommended)
- 24" Monitor or larger (portrait orientation, built-in speakers)
- Two-way mirror acrylic sheet
- USB Microphone with good pickup range
- 5V/4A Power Supply
- Custom frame for mounting

## Software Dependencies

```
Python 3.11+
Pygame 2.6         - Display rendering
OpenAI SDK         - AI voice interaction
SpeechRecognition  - Voice input
gTTS               - Text-to-speech fallback
ElevenLabs API     - Premium TTS (optional)
WebSocket-client   - Realtime API + OpenClaw
yfinance           - Stock market data
feedparser         - RSS news headlines
psutil             - System monitoring
python-fitbit      - Fitbit health data
Google Calendar API - Calendar events
requests           - HTTP APIs (weather, Home Assistant)
```

## Quick Start

1. **Clone the repository:**
```bash
git clone https://github.com/DanDon01/AI-Mirror.git
cd AI-Mirror
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure API credentials:**

Create `Variables.env` in the **parent directory** (one level above the repo) with your API keys:
```bash
# OpenAI API (required for voice interaction)
OPENAI_API_KEY=your_key

# Weather (optional -- falls back to Open-Meteo which needs no key)
OPENWEATHERMAP_API_KEY=your_key

# Fitbit API (optional)
FITBIT_CLIENT_ID=your_id
FITBIT_CLIENT_SECRET=your_secret
FITBIT_ACCESS_TOKEN=your_token
FITBIT_REFRESH_TOKEN=your_refresh_token

# Google Calendar API (optional)
GOOGLE_CLIENT_ID=your_id
GOOGLE_CLIENT_SECRET=your_secret
GOOGLE_ACCESS_TOKEN=your_token
GOOGLE_REFRESH_TOKEN=your_refresh_token

# ElevenLabs API (optional, premium TTS)
ELEVENLABS_API_KEY=your_key
ELEVENLABS_VOICE_ID=your_voice_id

# OpenClaw Gateway (optional, messaging)
OPENCLAW_GATEWAY_URL=wss://your-gateway
OPENCLAW_GATEWAY_TOKEN=your_token

# Home Assistant (optional, smart home)
HA_URL=http://your-ha-ip:8123
HA_TOKEN=your_long_lived_access_token
```

Modules auto-hide when their credentials aren't configured, so you can start with just the basics and add integrations over time.

4. **Run the application:**
```bash
python AI-Mirror.py
```

## Controls

| Key | Action |
|-----|--------|
| `Space` | Trigger voice interaction |
| `s` | Cycle state: active -> screensaver -> sleep -> active |
| `d` | Toggle debug overlay (red grid + module bounds) |
| `q` / `Esc` | Quit |
| `1` | Toggle Weather |
| `2` | Toggle Calendar |
| `3` | Toggle Countdown |
| `4` | Toggle Smart Home |
| `5` | Toggle Greeting |
| `6` | Toggle Quote |
| `7` | Toggle News |
| `8` | Toggle Fitbit |
| `9` | Toggle OpenClaw |
| `0` | Toggle System Info |

## Layout

The mirror uses a zone-based layout optimized for portrait displays:

| Zone | Position | Content |
|------|----------|---------|
| Top bar | Full width, top | Scrolling clock + static date + weather summary |
| Left column | 22% width, left edge | Weather, Calendar, Countdown, Smart Home |
| Right column | 22% width, right edge | Greeting, Quote, News, Fitbit, OpenClaw, System Info |
| Center | 56% width, middle | Clear for reflection. AI overlays + notifications when active |
| Bottom bar | Full width, bottom | Scrolling stock ticker |

Screen resolution is auto-detected at startup. The layout adapts to 27", 24", and 21" portrait displays.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- OpenAI for GPT-4o and Realtime API
- ElevenLabs for premium text-to-speech
- Fitbit for their health data API
- OpenWeatherMap and Open-Meteo for weather data
- Home Assistant for smart home integration
- The Raspberry Pi Foundation
- Contributors and the open-source community

---
<div align="center">
Made by DanDon01
</div>
