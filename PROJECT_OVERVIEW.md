# AI-Mirror - Technical Project Overview

## What Is This?

An interactive AI-powered smart mirror built on a Raspberry Pi 5. A portrait-oriented monitor sits behind two-way mirror acrylic in a custom frame. The Pi runs a fullscreen Pygame application that displays real-time information modules and provides voice-activated AI conversation.

## Architecture

```
+---------------------------------------------------------------+
|                    AI-Mirror.py (Main Loop)                    |
|  - Pygame init, event handling, state machine                 |
|  - 30 FPS render loop                                         |
|  - States: active / screensaver / sleep                       |
+-------+---------------------------+---------------------------+
        |                           |
+-------v--------+        +--------v---------+
| ModuleManager  |        | LayoutManager    |
| - Init order   |        | - 2-column grid  |
| - Visibility   |        | - Position calc  |
| - Voice fallback|       | - Module sizing  |
+-------+--------+        +------------------+
        |
        v
+---------------------------------------------------------------+
|                     DISPLAY MODULES                           |
|                                                               |
|  clock_module.py        Scrolling time, centered date         |
|  weather_module.py      OpenWeatherMap + Open-Meteo + animated effects|
|  stocks_module.py       yfinance, 8 tickers, US/UK markets   |
|  calendar_module.py     Google Calendar, OAuth2, color-coded  |
|  fitbit_module.py       Steps, calories, sleep, heart rate    |
|  retrocharacters_module.py  Falling retro icons screensaver   |
|  smarthome_module.py    Stub - not yet functional             |
+---------------------------------------------------------------+
        |
        v
+---------------------------------------------------------------+
|                   VOICE / AI MODULES                          |
|                                                               |
|  Priority 1: elevenvoice_module.py                            |
|    ElevenLabs TTS (eleven_multilingual_v2) + Google STT       |
|    + GPT-4o                                                   |
|                                                               |
|  Priority 2: ai_voice_module.py                               |
|    OpenAI Realtime API (gpt-4o-realtime-preview) via WebSocket|
|    Direct audio streaming, 24kHz sample rate                  |
|    Currently in test mode (pre-recorded WAV)                  |
|                                                               |
|  Fallback:  AI_Module.py                                      |
|    GPT-4o Chat API + Google STT                               |
|    OpenAI TTS (gpt-4o-mini-tts) primary, gTTS fallback       |
+---------------------------------------------------------------+
        |
        v
+---------------------------------------------------------------+
|                   EXTERNAL APIS                               |
|                                                               |
|  OpenAI        - Realtime API, Chat Completions, TTS, Models  |
|  ElevenLabs    - Text-to-Speech (premium voices)              |
|  OpenWeatherMap - Current weather (primary, requires key)     |
|  Open-Meteo    - Current weather (free fallback, no key)      |
|  Google Calendar - Events via OAuth2                          |
|  Fitbit        - Health data via OAuth2                       |
|  Yahoo Finance - Stock quotes via yfinance                    |
+---------------------------------------------------------------+
```

## Module Interface

Every display module implements this interface:

```python
class SomeModule:
    def __init__(self, **params):  # Config from config.py
        pass
    def update(self):              # Called each frame, fetch data on intervals
        pass
    def draw(self, screen, position):  # Render to pygame surface
        pass
    def cleanup(self):             # Release resources on shutdown
        pass
```

Position is a dict: `{'x': int, 'y': int, 'width': int, 'height': int}`

## Data Flow

### Voice Interaction
```
User presses SPACE
  -> MagicMirror.handle_events()
  -> ai_voice_module.on_button_press()
  -> stream_audio() in background thread
  -> Audio captured (currently test WAV, future: live mic via arecord)
  -> PCM16 chunks base64-encoded
  -> Sent via WebSocket to OpenAI Realtime API
  -> Response audio chunks received
  -> Decoded and played via pygame.mixer
```

### Module Data Refresh
```
Main loop calls update_modules() each frame
  -> Each module checks its update interval
  -> If interval elapsed:
       weather: OpenWeatherMap or Open-Meteo fallback (30 min interval)
       stocks:  yfinance API call (10/30 min interval)
       calendar: Google Calendar API (1 hour interval)
       fitbit:  Fitbit API (daily sync)
  -> Data stored in module instance
  -> draw() renders current data to screen
```

## Configuration System

All config lives in `config.py` which loads `Variables.env` for secrets.

```
config.py
  |- MONITOR_CONFIGS    3 presets (27", 24", 21" portrait)
  |- CURRENT_MONITOR    Active monitor profile
  |- LAYOUT             Grid spacing, font sizes, backgrounds
  |- CONFIG             Main config dict:
       |- screen         Fullscreen, size, scale
       |- clock          Time/date format, timezone
       |- weather        API key, city, icons path
       |- stocks         Ticker symbols list
       |- calendar       Google OAuth credentials
       |- fitbit         Fitbit OAuth credentials
       |- ai_voice       OpenAI config, audio device
       |- ai_interaction Fallback AI config
       |- eleven_voice   ElevenLabs config
       |- module_visibility  Show/hide per module
       |- screensaver_modules  Active during screensaver
       |- sleep_modules  Active during sleep
       |- debug          Debug mode, log level
       |- visual_effects Animation settings
```

## Current State (as of Feb 2026)

### Working
- Clock module (time/date display)
- Weather module (OpenWeatherMap, animated effects)
- Stocks module (8 tickers, market-aware updates)
- Calendar module (Google Calendar, OAuth2, color-coded events)
- Fitbit module (steps, calories, sleep, heart rate)
- Retro characters screensaver
- AI voice module (WebSocket connection to OpenAI Realtime API)
- AI interaction module (fallback GPT-4 with speech recognition)
- ElevenLabs voice module (premium TTS)
- Module visibility toggling via voice commands
- State cycling (active/screensaver/sleep)
- Layout system with multiple monitor profiles
- Logging with rotating file handlers

### Not Yet Implemented
- Live microphone recording (ai_voice uses test WAV file)
- Gesture recognition / hand control
- PIR / presence detection (auto wake/sleep)
- Camera-based face detection
- Smart home integration (module is a stub)
- Package delivery tracking
- Automatic brightness adjustment
- Realtime avatar display
- Local AI model support (Ollama)

### Known Issues (remaining)
- No thread safety on shared CONFIG/visibility state
- `ai_voice_module.py` uses a test WAV file instead of live mic (intentional for now)
- Audio device indices are hardware-specific, may need reconfiguration per Pi setup

## Tech Stack

| Component | Library/Service | Version |
|-----------|----------------|---------|
| Display | Pygame | 2.6.0 |
| AI (realtime) | OpenAI Realtime API | gpt-4o-realtime-preview |
| AI (fallback) | OpenAI Chat API | gpt-4o |
| TTS (primary) | OpenAI TTS | gpt-4o-mini-tts |
| TTS (premium) | ElevenLabs API | eleven_multilingual_v2 |
| TTS (fallback) | gTTS | latest |
| STT | Google Speech Recognition | via speech_recognition |
| Weather (primary) | OpenWeatherMap API | v2.5 |
| Weather (fallback) | Open-Meteo API | v1 (free, no key) |
| Stocks | yfinance | 0.2.42 |
| Calendar | Google Calendar API | v3 |
| Health | Fitbit API | via fitbit 0.3.1 |
| Audio I/O | PyAudio / pygame.mixer | - |
| WebSocket | websocket-client | - |
| Config | python-dotenv | 1.0.1 |

## Keyboard Controls

| Key | Action |
|-----|--------|
| `Space` | Trigger voice interaction |
| `s` | Cycle state: active -> screensaver -> sleep -> active |
| `d` | Toggle debug mode |
| `q` | Quit application |
| `Esc` | Cancel recording (in AI_Module) |

## File Tree
```
AI-Mirror/
  AI-Mirror.py              Main application
  config.py                 Configuration hub
  module_manager.py         Module lifecycle
  layout_manager.py         Position/layout
  ai_voice_module.py        OpenAI Realtime voice
  AI_Module.py              Fallback AI + speech
  elevenvoice_module.py     ElevenLabs voice
  clock_module.py           Clock display
  weather_module.py         Weather display
  stocks_module.py          Stock ticker
  calendar_module.py        Calendar events
  fitbit_module.py          Health data
  retrocharacters_module.py Screensaver
  smarthome_module.py       Smart home (stub)
  visual_effects.py         Shared visual utils
  voice_commands.py         Command parser
  weather_animations.py     Weather effects
  whispertest.py            Whisper test utility
  MagicMirror.__init__      Package marker
  fallback_responses.json   Offline AI responses
  requirements.txt          Python dependencies
  Variables.env             API keys (gitignored)
  LICENSE                   MIT License
  README.md                 Project readme
  CLAUDE.md                 Claude Code instructions
  PROJECT_OVERVIEW.md       This file
  assets/
    retro_icons/            27 PNG character sprites
    weather_icons/          9 PNG weather animations
    sound_effects/          4 MP3 audio files
  documentation/
    code_structure.md       Basic structure diagram
```
