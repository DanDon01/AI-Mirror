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
| London, UK |                  | Good morning|
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

Copy the example settings to the **parent directory** (one level above the
repo, so they can never be committed) and fill in only what you use:
```bash
cp Variables.env.example ../Variables.env
```

Modules auto-hide when their credentials aren't configured, so you can start
with just the basics and add integrations over time. Weather falls back to
Open-Meteo, which needs no key.

4. **Make it your home (optional):**
```bash
cp -r house.example house
```
See [Make it your home](#make-it-your-home) below.

5. **Run the application:**
```bash
python AI-Mirror.py
```

On a Raspberry Pi, `deploy/install-service.sh visual` installs the mirror as a
service that boots into the browser front end (`prototype/visual-gate`);
`deploy/install-service.sh pygame` boots the Pygame app instead.

## Make it your home

Everything specific to one home lives in a **house pack**, a folder outside
the code: `house/` in the checkout (gitignored) or anywhere you point
`MIRROR_HOUSE_DIR` at. Start from [`house.example/`](house.example/), which
explains each file. A pack can hold:

- `config_local.py` - your city, stock watchlist and module tweaks
- `avatars/` - your talking characters: portraits, `profiles.json`, persona prompts
- `theatre/` - generated in-character clips that cover the avatar's pauses
- `visual-gate/` - your own versions of front-end files, such as a 3D model
  of your house (`js/home-twin.js`) in place of the example house

Keep your pack in its own **private** repo if you want it versioned;
`deploy/deploy.sh` pulls it along with the code.

**Privacy:** never commit `Variables.env` or your house pack to a public repo.
Home Assistant entity IDs belong in `Variables.env`, not in code.

### Selectable talking avatars

The avatar is a character you talk to: press SPACE, speak, press SPACE again,
and it answers in a generated talking video (local Vosk speech-to-text ->
OpenAI text -> Fal video with speech). Characters come from your house pack:
list them in `avatars/profiles.json`, add a portrait and a persona prompt for
each (see [`house.example/README.md`](house.example/README.md)). The LAN web
panel picks the character and remembers the choice across restarts.

Install a Vosk model separately and set `VOSK_MODEL_PATH`, plus `FAL_KEY` and
`OPENAI_API_KEY`. Set `AVATAR_PROMPT_FILE` to use one prompt for every
character, `AVATAR_SYSTEM_PROMPT` for a one-line override, or
`AVATAR_CHARACTER=<key>` to override the remembered selection at startup.

On a Pi the avatar keeps a warm microphone stream and recogniser ready, keeps
a short pre-roll so a first word said while pressing SPACE is not lost, and
submits the reply the moment you finish. Replies stream straight from Fal and
are cached afterwards when their intent and time of day make reuse safe.

`avatar_theatre.py` can generate short silent "theatre" clips per character
(appearing, thinking, idling) that the browser front end plays while a reply
is being made, so there is never a dead pause. Every paid call is capped by
hard hourly, daily and cost limits in `api_tracker.py`; run with `--check`
first to see what would be made and what it would cost.

### Daylight / night readability

The mirror uses a high-contrast midnight-glass palette: white primary text,
champagne module labels, and clear functional status colours. By default it
automatically uses a brighter daylight treatment from 07:00 to 20:59 and a
softer night treatment outside those hours. The body and small text are also
scaled up for reading through two-way mirror glass.

Optional `Variables.env` tuning, followed by a restart:

```env
UI_DISPLAY_MODE=auto
UI_DAY_BRIGHTNESS=1.18
UI_NIGHT_BRIGHTNESS=0.88
UI_TEXT_SCALE=1.12
```

Set `UI_DISPLAY_MODE=day` or `night` to force a mode, or set
`UI_BRIGHTNESS` to override the automatic brightness multiplier entirely.

### Future option: Fal Director realtime avatar

The active avatar path deliberately uses short, cached-or-generated MP4
responses. A possible future upgrade is
[Fal Director](https://fal.ai/models/minimax/h3-max/director/api), which can
maintain a continuous WebRTC video/audio stream from the approved reference
image and accept live prompt updates. That could make the character feel much
closer to a realtime conversation.

It is not enabled or integrated today: Fal documents Director as an
experimental alpha JavaScript/WebRTC API, while the mirror uses Python,
Pygame, and ffmpeg. Its prompt-only contract also needs a proof that spoken
dialogue follows Nano's response exactly before it can replace the current
reliable `Say exactly:` video flow. It should be built as an opt-in proof mode
with the current pipeline retained as fallback, and tested for first-frame
latency, dialogue accuracy, continuity, and continuous-session cost.

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
