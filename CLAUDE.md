# AI-Mirror - Project Instructions

## Overview
AI-powered smart mirror running on Raspberry Pi 5 with a portrait-oriented display behind two-way mirror acrylic. Built with Python and Pygame. Displays real-time information (clock, weather, stocks, calendar, Fitbit health data) and provides voice-activated AI interaction.

## How to Run
```bash
python AI-Mirror.py
```
Entry point: `AI-Mirror.py` -> `MagicMirror` class -> `run()` main loop at 30 FPS.

## Target Platform
- **Runtime:** Raspberry Pi 5 (8GB RAM), Raspberry Pi OS
- **Development:** Windows 11, VSCode terminal
- **Deployment:** Push from Windows via git, pull on Pi 5 to test
- **Display:** Portrait monitor (27" 1440x2560, 24" 1200x1920, or 21" 768x1024)
- **Audio:** USB microphone (ALSA device), built-in monitor speakers

## Project Conventions
- No emojis in code (not in strings, comments, or print statements)
- User does all video/visual testing on the Pi - Claude cannot see video output
- All API keys go in `Variables.env` (parent directory, gitignored) - never commit secrets
- Use `logging` module for all output, not `print()` statements
- Voice/audio features are Pi hardware-dependent and experimental
- Modules follow a standard interface: `__init__(config)`, `update()`, `draw(screen, position)`, `cleanup()`

## Architecture
```
AI-Mirror.py (main loop, event handling, screen init)
  -> ModuleManager (module lifecycle, visibility, voice fallback)
  -> LayoutManager (position calculation, 2-column grid)
  -> Display Modules:
       clock_module.py       - Time/date display
       weather_module.py     - OpenWeatherMap + Open-Meteo fallback + animations
       stocks_module.py      - yfinance stock tickers
       calendar_module.py    - Google Calendar events
       fitbit_module.py      - Fitbit health data
       retrocharacters_module.py - Screensaver animation
  -> Voice/AI Modules (priority order):
       elevenvoice_module.py - ElevenLabs TTS (eleven_multilingual_v2) + GPT-4o (newest)
       ai_voice_module.py    - OpenAI Realtime API WebSocket (gpt-4o-realtime-preview)
       AI_Module.py          - GPT-4o + OpenAI TTS (gpt-4o-mini-tts), gTTS fallback
  -> Support:
       config.py             - All configuration, loaded from Variables.env
       visual_effects.py     - Shared rendering utilities
       voice_commands.py     - "show/hide module" command parser
       weather_animations.py - Weather particle effects
```

## Key File Map
| File | Purpose | Lines |
|------|---------|-------|
| `AI-Mirror.py` | Main app, event loop, screen init | ~595 |
| `config.py` | All config, env vars, monitor profiles, colors | ~321 |
| `module_manager.py` | Module init, visibility, voice fallback | ~176 |
| `layout_manager.py` | Position calculation, module backgrounds | ~209 |
| `ai_voice_module.py` | OpenAI Realtime API via WebSocket | ~574 |
| `AI_Module.py` | Fallback GPT-4o + speech recognition + OpenAI TTS | ~890 |
| `elevenvoice_module.py` | ElevenLabs TTS integration | ~119 |
| `weather_module.py` | Dual-source weather (OpenWeatherMap + Open-Meteo) | ~280 |
| `stocks_module.py` | Stock ticker display | ~250 |
| `calendar_module.py` | Google Calendar integration | ~250 |
| `fitbit_module.py` | Fitbit health data | ~250 |
| `clock_module.py` | Time/date display | ~97 |
| `retrocharacters_module.py` | Falling retro icons screensaver | ~77 |
| `smarthome_module.py` | Smart home stub (not yet functional) | ~91 |
| `visual_effects.py` | Shared visual effect utilities | ~94 |
| `voice_commands.py` | Show/hide command parser | ~57 |
| `weather_animations.py` | Weather condition animations | ~150 |

## Environment Variables (Variables.env)
```
OPENAI_API_KEY=
OPENWEATHERMAP_API_KEY=
FITBIT_CLIENT_ID=
FITBIT_CLIENT_SECRET=
FITBIT_ACCESS_TOKEN=
FITBIT_REFRESH_TOKEN=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_ACCESS_TOKEN=
GOOGLE_REFRESH_TOKEN=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
```

## Application States
- **Active:** All modules visible, voice ready
- **Screensaver:** Retro character animation only
- **Sleep:** Clock module only
- Cycle with `s` key. `Space` triggers voice. `d` toggles debug. `q` quits.

## Known Gotchas
- `Variables.env` path is `os.path.join(current_dir, '..', 'Variables.env')` - file must be in parent directory
- Audio device indices are hardware-specific (USB mic typically card 2 or 3 on Pi)
- `ai_voice_module.py` currently uses a test WAV file for audio input (intentional during testing phase)
- ALSA error suppression in `AI-Mirror.py` is aggressive - may hide real audio errors
- `config.py` calls `pygame.font.init()` at import time (side effect)
- Voice activation/wake words are experimental - gesture control or PIR detection may replace them

## Future Direction
- Realtime avatar interaction on the mirror display
- Camera-based advanced interaction (presence detection, face recognition)
- Local AI models via Ollama on Windows PC over network (after API-based system is stable)
- Smart home integration via MQTT/Home Assistant
- Gesture control or PIR-based wake/sleep
