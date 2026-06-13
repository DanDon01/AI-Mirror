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
- **Minimal luxury:** platinum text on black -- primary (226,228,232), secondary (148,150,156), dim (96,98,104). Single champagne accent (196,174,128) for module labels and hairline rules only. Muted functional green/red/amber. Module labels are tracked uppercase with a short hairline rule. Full-width hairlines under the top banner and above the ticker frame the mirror space.
- **Typography:** Bundled Lato (assets/fonts, OFL) -- light weight for body/hero values, regular for small labels. load_font(weight, size) in config.py; SysFont stack is the fallback. Hero values (temperature, greeting, clock) are large and light.
- **Design preview:** `python design_preview.py` renders the full UI with fake data to data/preview.png headlessly -- judge design changes on the dev box before deploying.
- **Layout:** Zone-based with edge padding. Left column (22% width): weather, calendar, countdown, smarthome. Right column (22% width, right-aligned text): greeting, quote, news, fitbit, openclaw, sysinfo. Top bar: scrolling monospace clock + date + weather status. Bottom bar: scrolling stock ticker.
- **Center clear zone:** Reserved for mirror reflection. AI/voice overlays only appear when active. Center notification queue for alerts (stock moves, timer completion, new messages).
- **Fonts:** Segoe UI / DejaVu Sans (body), Consolas / DejaVu Sans Mono (clock). Sizes scaled for arm's length readability.
- **Animations:** Per-module eased fade transitions via AnimationManager with staggered boot. Headline rotation with crossfade.
- **Weather feature band:** The top of the screen reflects the sky (weather_animations.py) in an expanded band (~16% of screen height, EFFECT_H, fading out at the bottom into the mirror's clear centre): radiant rayed sun, big crescent moon + drifting stars, layered cloud banks, wind-slanted rain with splashes, drifting snow with depth, and dramatic storm lightning (full-band flash + bolt). Procedural soft-glow sprites + lines, no PNGs. Clouds keep clear of the time digits. Day/night picks sun vs moon; wind speed slants rain and adds gusts. Preview any condition: `python design_preview.py rain` (clear|partly|clouds|rain|storm|snow). The clock banner scrolls the time (config clock params `scrolling: True`).

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
       smarthome_module.py   - Home Assistant mini view (left column: summary + state dots)
                               plus on-demand center dashboard overlay (voice "show the
                               dashboard" or 'h' key; auto-closes after 60s)
       avatar_module.py      - Procedural talking-head avatar with audio-driven lipsync
       phone_module.py       - iPhone battery (HA Companion app) + leave-by countdown
                               computed from the calendar module's events
       sysinfo_module.py     - Pi system stats (CPU temp, memory, disk, uptime via psutil + /proc fallback)
       greeting_module.py    - Time-based greetings + rotating affirmations
       retrocharacters_module.py - Falling retro icons screensaver
  -> Voice/AI Modules (priority order):
       ai_voice_module.py    - OpenAI Realtime API GA WebSocket (gpt-realtime-mini default,
                               gpt-realtime-2 optional). Live mic conversations with server
                               VAD; feeds avatar lipsync + state hooks.
       AI_Module.py          - gpt-5.4-mini chat + OpenAI TTS (pinned gpt-4o-mini-tts
                               snapshot), gTTS fallback
       elevenvoice_module.py - ElevenLabs TTS (eleven_multilingual_v2) + gpt-5.4-mini
  -> Support:
       config.py             - All configuration, colors, fonts, layout zones, env vars
       web_panel.py          - LAN phone control panel (http://<pi-ip>:8780): state,
                               module toggles, API usage, log tail. Stdlib HTTP server;
                               writes go through a command queue drained by the main loop.
       data_cache.py         - Last-good payload cache (weather/news/calendar restore
                               instantly after reboot, then refresh in background)
       background_fetcher.py - Runs module network fetches on daemon threads (never
                               block the 30 FPS render loop); results polled in update()
       api_tracker.py        - API rate limits, cost tracking, and circuit breaker
                               (3 consecutive failures -> 30 min backoff per service)
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

## Deployment (Pi as an appliance)
- `deploy/ai-mirror.service` - systemd unit (auto-restart, start on boot). Adjust
  User/WorkingDirectory, then `sudo cp` to /etc/systemd/system and enable.
- `deploy/deploy.sh` - run on the Pi: git pull, pip install, smoke test, restart service.
- `smoke_test.py` - headless import + 30-frame draw test; CI runs it on every push
  (`.github/workflows/ci.yml`). Run it before restarting the mirror after changes.
- Web panel at `http://<pi-ip>:8780` replaces keyboard controls once wall-mounted
  (no auth - home LAN only; disable via `web_panel.enabled` in config.py).

## Keyboard Controls
| Key | Action |
|-----|--------|
| `s` | Cycle state: active -> screensaver -> sleep -> active |
| `Space` | Trigger voice interaction (AI module) |
| `d` | Toggle debug overlay (red grid + module bounds) |
| `h` | Toggle Home Assistant dashboard overlay |
| `q` / `Esc` | Quit application |
| `1`-`9`, `0` | Toggle module visibility (1=weather, 2=calendar, 3=countdown, 4=smarthome, 5=greeting, 6=quote, 7=news, 8=fitbit, 9=openclaw, 0=sysinfo) |

## Application States
- **Active:** All enabled modules visible, voice ready, weather animations active
- **Screensaver:** Retro character animation + clock only
- **Sleep:** Clock module only (minimal display)
- State transitions use fade animations via AnimationManager

## API Lifecycle Notes (June 2026)
- OpenAI Realtime API: migrated to the GA interface (beta removed May 2026). No
  OpenAI-Beta header; session.update requires `type: "realtime"` and nested audio
  config; server events are `response.output_audio.delta` etc.
- Voice model: `gpt-realtime-mini` (cost/latency sweet spot); switch to
  `gpt-realtime-2` in config for reasoning-class conversation.
- TTS uses the pinned `gpt-4o-mini-tts-2025-12-15` snapshot (unversioned alias
  shuts down 2026-07-23).
- Fitbit legacy Web API retires September 2026; Google Health API (Google Cloud +
  Google OAuth + user re-consent) is the replacement. fitbit_module detects HTTP 410
  and shows "Fitbit API retired" instead of hammering the dead endpoint.
- yfinance was bumped 0.2.x -> 1.x in requirements.txt; verify the stock ticker on
  the Pi after upgrading.

## Avatar (talking head, "Holly" style)
- `avatar_module.py` composites pre-rendered realistic face frames from
  `assets/avatar/` (neutral/blink/smile + mouth visemes; see README.txt there)
  semi-transparent on black with optional CRT scanlines. Centered in the
  mirror's clear zone, visible only during voice interaction, smiles when the
  conversation ends, fades out after 5 s idle.
- Lipsync: the voice playback thread calls `avatar.feed_audio(pcm)`; RMS picks
  mouth openness, zero-crossing rate separates fricatives from vowels, and the
  nearest available viseme frame is shown. Blinks are random (2-6 s).
- Frames are produced OFFLINE (photos of a real face, or LivePortrait on the
  dev PC from a single photo). Neural talking heads are not real-time on a
  Pi 5; frame compositing at 30 FPS is the intended approach.
- Falls back to a simple procedural face when assets/avatar/ has no frames.

## Known Gotchas
- `Variables.env` path is `os.path.join(current_dir, '..', 'Variables.env')` - file must be in parent directory
- Screen resolution is auto-detected at startup (`pygame.display.Info()`) - config values are overridden with actual display size
- Audio device indices are hardware-specific (USB mic typically card 2 or 3 on Pi)
- `ai_voice_module.py` streams the live USB mic via arecord + plughw (ALSA resamples to 24 kHz); SPACE toggles a hands-free conversation with server-side semantic VAD. Falls back to the test WAV (manual commit) when arecord/mic is unavailable, e.g. on the Windows dev box. Mic is gated while the mirror speaks (no barge-in).
- All display modules fetch over the network via `BackgroundFetcher` - update() submits a fetch and polls the result on later frames; never call requests directly in update()
- Spoken commands ride the Realtime API's user transcript: ai_voice's command listener queues each utterance, the main loop parses it (dashboard phrases + voice_commands.py show/hide). The AI also replies conversationally to these - it does not know a command fired.
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
