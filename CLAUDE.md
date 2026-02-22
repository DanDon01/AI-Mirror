# AI-Mirror - Project Instructions

## Overview
AI-powered smart mirror running on Raspberry Pi 5 with a portrait-oriented display behind two-way mirror acrylic. Built with Python and Pygame. Features a zone-based mirror-optimized UI with edge-hugging modules, scrolling clock/stock bars, right-aligned right-column text, and a clear center for reflection. Displays real-time information (weather, stocks, calendar, news, Fitbit, smart home, system stats) and provides voice-activated AI interaction.

## How to Run
```bash
python AI-Mirror.py
```
Entry point: `AI-Mirror.py` -> `MagicMirror` class -> `run()` main loop at 30 FPS.

## Target Platform
- **Runtime:** Raspberry Pi 5 (8GB RAM), Raspberry Pi OS
- **Development:** Windows 11, VSCode terminal
- **Deployment:** Push from Windows via git, pull on Pi 5 to test
- **Display:** Portrait monitor (27" 1440x2560, 24" 1200x1920, or 21" 768x1024). Auto-detects native resolution at startup.
- **Audio:** USB microphone (ALSA device), built-in monitor speakers

## Project Conventions
- No emojis in code (not in strings, comments, or print statements)
- User does all video/visual testing on the Pi - Claude cannot see video output
- All API keys go in `Variables.env` (parent directory, gitignored) - never commit secrets
- Use `logging` module for all output, not `print()` statements
- Voice/audio features are Pi hardware-dependent and experimental
- Modules follow a standard interface: `__init__(config)`, `update()`, `draw(screen, position)`, `cleanup()`
- Position dicts include `align: 'right'` for right-column modules; use `ModuleDrawHelper.blit_aligned()` for text placement

## UI Design
- **Mirror-optimized:** Pure black background (transparent through two-way mirror glass), no module backgrounds or boxes
- **Color palette:** Soft text on black -- primary (185,185,190), secondary (140,140,145), dim (90,90,95). Blue module titles (70,140,220). Cyan clock face (90,195,255).
- **Layout:** Zone-based with edge padding. Left column (22% width): weather, calendar, countdown, smarthome. Right column (22% width, right-aligned text): greeting, quote, news, fitbit, openclaw, sysinfo. Top bar: scrolling monospace clock + date + weather status. Bottom bar: scrolling stock ticker.
- **Center clear zone:** Reserved for mirror reflection. AI/voice overlays only appear when active. Center notification queue for alerts (stock moves, timer completion, new messages).
- **Fonts:** Segoe UI / DejaVu Sans (body), Consolas / DejaVu Sans Mono (clock). Sizes scaled for arm's length readability.
- **Animations:** Per-module fade transitions via AnimationManager. Weather particle effects (clouds, rain, sun, snow, storm). Headline rotation with crossfade.

## Architecture
```
AI-Mirror.py (main loop, event handling, screen auto-detect, state machine)
  -> ModuleManager (module lifecycle, visibility, voice fallback chain)
  -> LayoutManager (zone-based positioning, left/right column stacking)
  -> AnimationManager (fade transitions, state transitions, center notifications)
  -> ModuleDrawHelper (shared fonts, titles, separators, right-alignment)
  -> SurfaceCache (per-module render caching for performance)
  -> Display Modules:
       clock_module.py       - Scrolling top bar: monospace time, static date, weather status
       weather_module.py     - OpenWeatherMap + Open-Meteo fallback + weather animations
       stocks_module.py      - Scrolling bottom ticker (yfinance, batch + history fallback)
       calendar_module.py    - Google Calendar events
       fitbit_module.py      - Fitbit health data + step progress bar
       countdown_module.py   - Event countdowns + voice timer + center alerts
       quote_module.py       - Daily quote (ZenQuotes API + local JSON + builtin fallback)
       news_module.py        - RSS news headlines (feedparser) + breaking news notifications
       openclaw_module.py    - OpenClaw Gateway multi-channel inbox (WebSocket)
       smarthome_module.py   - Home Assistant entity states (REST API, auto-discover)
       sysinfo_module.py     - Pi system stats (CPU temp, memory, disk, uptime via psutil + /proc fallback)
       greeting_module.py    - Time-based greetings + rotating affirmations
       retrocharacters_module.py - Falling retro icons screensaver
  -> Voice/AI Modules (priority order):
       elevenvoice_module.py - ElevenLabs TTS (eleven_multilingual_v2) + GPT-4o
       ai_voice_module.py    - OpenAI Realtime API WebSocket (gpt-4o-realtime-preview)
       AI_Module.py          - GPT-4o + OpenAI TTS (gpt-4o-mini-tts), gTTS fallback
  -> Support:
       config.py             - All configuration, colors, fonts, layout zones, env vars
       module_base.py        - ModuleDrawHelper, SurfaceCache, shared draw utilities
       animation_manager.py  - Fade transitions, state transitions, center notifications
       layout_manager.py     - Zone-based position calculation with alignment
       visual_effects.py     - Shared rendering utilities
       voice_commands.py     - "show/hide module" command parser
       weather_animations.py - Weather particle effects (cloud, rain, sun, storm, snow)
```

## Key File Map
| File | Purpose | Lines |
|------|---------|-------|
| `AI-Mirror.py` | Main app, event loop, screen auto-detect, state machine, module toggle | ~700 |
| `config.py` | Colors, fonts, layout zones, monitor configs, all module params | ~460 |
| `module_base.py` | ModuleDrawHelper (fonts, titles, alignment), SurfaceCache | ~110 |
| `animation_manager.py` | Fade transitions, state transitions, center notification queue | ~100 |
| `layout_manager.py` | Zone-based positioning, column stacking, right-align tagging | ~140 |
| `module_manager.py` | Module init, visibility, voice fallback chain | ~176 |
| `clock_module.py` | Scrolling top bar: monospace time, clipped scroll, static date | ~128 |
| `weather_module.py` | Dual-source weather (OpenWeatherMap + Open-Meteo) + animations | ~327 |
| `stocks_module.py` | Bottom ticker: batch + history fallback, scrolling render | ~480 |
| `calendar_module.py` | Google Calendar integration | ~250 |
| `fitbit_module.py` | Fitbit health data + thin progress bars | ~362 |
| `countdown_module.py` | Event countdowns + voice-activated timer + center alerts | ~190 |
| `quote_module.py` | Daily quote (ZenQuotes API / local JSON / builtin) | ~202 |
| `news_module.py` | RSS headlines via feedparser + breaking news notifications | ~189 |
| `openclaw_module.py` | OpenClaw Gateway WebSocket client | ~386 |
| `smarthome_module.py` | Home Assistant REST API, auto-discover entities, domain coloring | ~210 |
| `sysinfo_module.py` | CPU temp, memory, disk, uptime (psutil + /proc/meminfo + statvfs) | ~290 |
| `greeting_module.py` | Time-based greetings + rotating affirmations | ~189 |
| `retrocharacters_module.py` | Falling retro icons screensaver | ~77 |
| `ai_voice_module.py` | OpenAI Realtime API via WebSocket | ~574 |
| `AI_Module.py` | Fallback GPT-4o + speech recognition + OpenAI TTS | ~890 |
| `elevenvoice_module.py` | ElevenLabs TTS integration | ~119 |
| `visual_effects.py` | Shared visual effect utilities | ~94 |
| `voice_commands.py` | Show/hide command parser | ~57 |
| `weather_animations.py` | Weather condition particle effects | ~150 |

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
OPENCLAW_GATEWAY_URL=
OPENCLAW_GATEWAY_TOKEN=
HA_URL=
HA_TOKEN=
```

## Keyboard Controls
| Key | Action |
|-----|--------|
| `s` | Cycle state: active -> screensaver -> sleep -> active |
| `Space` | Trigger voice interaction (AI module) |
| `d` | Toggle debug overlay (red grid + module bounds) |
| `q` / `Esc` | Quit application |
| `1`-`9`, `0` | Toggle module visibility (1=weather, 2=calendar, 3=countdown, 4=smarthome, 5=greeting, 6=quote, 7=news, 8=fitbit, 9=openclaw, 0=sysinfo) |

## Application States
- **Active:** All enabled modules visible, voice ready, weather animations active
- **Screensaver:** Retro character animation + clock only
- **Sleep:** Clock module only (minimal display)
- State transitions use fade animations via AnimationManager

## Known Gotchas
- `Variables.env` path is `os.path.join(current_dir, '..', 'Variables.env')` - file must be in parent directory
- Screen resolution is auto-detected at startup (`pygame.display.Info()`) - config values are overridden with actual display size
- Audio device indices are hardware-specific (USB mic typically card 2 or 3 on Pi)
- `ai_voice_module.py` currently uses a test WAV file for audio input (intentional during testing phase)
- ALSA error suppression in `AI-Mirror.py` is aggressive - may hide real audio errors
- `config.py` calls `pygame.font.init()` at import time (side effect)
- Voice activation/wake words are experimental - gesture control or PIR detection may replace them
- yfinance can get rate-limited by Yahoo Finance; the module has 6-hour backoff and history-based fallback
- Modules auto-hide when unconfigured (openclaw without gateway URL, smarthome without HA URL)

## Future Direction
- Realtime avatar interaction on the mirror display
- Camera-based advanced interaction (presence detection, face recognition)
- Local AI models via Ollama on Windows PC over network (after API-based system is stable)
- Voice commands for module toggle ("hide weather", "show fitbit")
- Gesture control or PIR-based wake/sleep
- Web-based frontend as alternative to Pygame
