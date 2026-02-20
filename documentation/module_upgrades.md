# AI-Mirror: Module Upgrade Suggestions

Per-module upgrade ideas categorised by Visual, Data/API, Performance, UX, and Accessibility.

---

## clock_module.py

**Visual:**
- Configurable scroll speed (currently hardcoded `0.7` in two places -- lines 18 and 44 both set it)
- Add smooth fade-in/fade-out at screen edges for the scrolling text (use VisualEffects gradient masking)
- Add analog clock mode option alongside digital
- Support custom TTF font files (the `font_file` param exists but is never used)

**Data/API:**
- World clock: display multiple timezones from config as smaller secondary clocks
- Sunrise/sunset times by consuming weather data from WeatherModule (inter-module data sharing)

**Performance:**
- Cache rendered time text surfaces when the time string hasn't changed (currently re-renders every frame)
- The `format_date` method has a hardcoded "Sep" -> "Sept" special case -- use locale-aware formatting

**UX:**
- Static mode option where time is centered rather than scrolling
- Configurable scroll direction (left-to-right or right-to-left)

**Accessibility:**
- Configurable font sizes independent of other modules
- High contrast mode option

---

## weather_module.py

**Visual:**
- Replace hardcoded `module_width = 225` and `module_height = 200` with config-driven dimensions
- Add 5-day forecast display (horizontal icons below current conditions)
- Add hourly temperature graph using `pygame.draw.lines`
- Clip weather animations to module bounding rect (currently draw to full screen)

**Data/API:**
- "Chance of rain" currently uses cloud coverage as proxy. Use Open-Meteo's `precipitation_probability` field
- Add UV index from Open-Meteo (`uv_index` parameter)
- Add air quality index (Open-Meteo has an AQI endpoint)
- Cache weather data to disk so the module shows last-known data on startup

**Performance:**
- Font initialization check runs every frame (`if not hasattr(self, 'title_font')`). Move to `__init__`
- Weather animation objects are recreated on every data refresh. Only recreate if condition actually changed

**UX:**
- Configurable units (Celsius/Fahrenheit, m/s vs mph)
- Show "Last updated: X minutes ago" timestamp
- Location name with country flag icon

**Accessibility:**
- Temperature color coding should offer a colorblind-safe alternative palette

---

## stocks_module.py

**Visual:**
- Mini sparkline charts (7-day price trend) next to each ticker using `pygame.draw.lines`
- Market open/closed indicator badge with timezone awareness
- Replace hardcoded `module_width = 225` with config dimensions

**Data/API:**
- yfinance is unstable with rate limiting. Add Alpha Vantage or Finnhub.io as fallback data source
- Add cryptocurrency support (BTC, ETH) via CoinGecko free API
- Add forex pairs (GBP/USD, EUR/GBP) via exchangerate-api.com
- Remove hardcoded fallback data (only covers 4 tickers), persist real data to disk cache instead

**Performance:**
- `time.sleep(1.0)` in the update loop blocks the main thread. Move all API calls to a background thread
- Remove `update_data()` method -- appears to be dead code duplicating `update_tickers_batch()`

**UX:**
- Voice-add tickers ("add AMZN to stocks")
- Market hours countdown ("US market opens in 2h 15m")
- Portfolio value tracking if quantities are configured

**Accessibility:**
- Up/down arrows should also have text prefix (`+`/`-`) for colorblind users

---

## calendar_module.py

**Visual:**
- Configurable event count (currently hardcoded to 8)
- Countdown timer for next upcoming event ("Meeting in 45 min")
- Multi-calendar support with distinct color coding per calendar (currently only reads `primary`)
- All-day event visual differentiation (banner style vs time-slot)

**Data/API:**
- `datetime.datetime.utcnow()` is deprecated in Python 3.12+. Replace with `datetime.now(timezone.utc)`
- Cache events to disk so events display on startup before first API call
- Add recurring event indicators
- Multiple Google account support

**Performance:**
- The `colors` API call happens on every update. Cache the color map (almost never changes)
- Font initialization runs every draw frame. Move to `__init__`

**UX:**
- "Today", "Tomorrow", "This Week" section headers
- Event duration display
- Voice-dismiss or acknowledge events

**Accessibility:**
- Event color indicator bar (5px) is too small for a hallway mirror. Make width configurable

---

## fitbit_module.py

**Visual:**
- Circular progress ring for steps instead of rectangular progress bar
- 7-day step trend mini-chart (bar graph)
- Heart rate zone indicator (resting/fat burn/cardio/peak)

**Data/API:**
- Step goal is hardcoded at 10,000. Fetch actual goal from Fitbit `user-profile` endpoint
- Sleep data only fetches yesterday. Add 7-day sleep trend
- Add weight/BMI tracking (if user has Fitbit scale)
- Add water intake tracking

**Bug Fix:**
- `self.effects` is referenced in `draw()` but never initialized in `__init__`. Add `self.effects = VisualEffects()`

**Performance:**
- Excessive debug logging runs every update cycle. Gate behind debug flag
- Token refresh should cache in-memory first and batch-write to disk

**UX:**
- Goal achievement celebration animation
- Configurable metrics display (choose which stats to show)
- "Streak" counter for consecutive days meeting step goal

**Accessibility:**
- Progress bar colors (red/yellow/green) should also show percentage text for colorblind users

---

## retrocharacters_module.py

**Visual:**
- Clamp rotation angle to [0, 360] to prevent unbounded accumulation
- Icon glow or trail effect as they fall
- New animation modes: "matrix rain", "bubble float", "orbit"

**Performance:**
- `pygame.transform.rotate` called every frame for every icon. Cache rotated versions at common angles (every 5 degrees)

**UX:**
- Interactive mode: icons respond to voice activation or button press
- Configurable icon sets (holiday themes, game themes)
- Time-of-day themes (daytime/nighttime different sets)

---

## smarthome_module.py

**Full overhaul needed** (currently 89-line stub):

**Visual:**
- Device status icons, on/off toggle indicators
- Room-based grouping with collapsible sections
- Energy usage graphs

**Data/API:**
- Add MQTT support as alternative to REST (lower latency for real-time state changes)
- Add Home Assistant WebSocket API for event subscriptions (push updates instead of polling)
- Add scene/automation trigger support
- Add device discovery

**Performance:**
- Currently polls each entity sequentially. Batch requests or use asyncio

**UX:**
- Voice command integration: "Turn off living room lights", "Set thermostat to 20"
- Quick-action touch regions rendered on the mirror

---

## ai_voice_module.py

**Visual:**
- Waveform visualization during recording (render PCM data as oscilloscope display)
- Animated "thinking" indicator during processing
- Transcript display with typing animation

**Data/API:**
- Replace test WAV file with live mic recording via `arecord` subprocess (infrastructure already exists in `check_alsa_sanity`)
- Add conversation history (multi-turn context via Realtime API session)
- Add function calling to allow AI to control mirror modules

**Performance:**
- Debug file writing generates many files. Add automatic cleanup of files older than 24 hours
- `time.sleep(2)` calls during init are synchronous blockers. Make init async or background

**UX:**
- Wake word activation ("Mirror") instead of requiring spacebar
- Visual feedback during each state transition
- Timeout auto-cancel for recording

---

## AI_Module.py

**Visual:**
- Unify draw styling with CONFIG system (currently uses custom hardcoded colors)
- Chat history display (last 3 exchanges as scrolling log)

**Data/API:**
- Context awareness: inject current weather, calendar events, and time into the system prompt
- Add function calling to GPT-4o for structured module control (replace regex-based parser)
- Conversation persistence between sessions (save to JSON in `data/`)

**Performance:**
- `DirectMicrophone` creates/destroys PyAudio instance on every `__enter__/__exit__`. Use persistent instance
- Multiple methods duplicate audio initialization logic. Consolidate into single audio manager

**UX:**
- Configurable system prompt personality
- Multi-language STT/TTS support
- "What did you say?" replay of last AI response

---

## elevenvoice_module.py

**Critical:**
- Add missing `draw(self, screen, position)` and `cleanup(self)` methods to conform to module interface
- Currently cannot be used as a display module

**Data/API:**
- Voice selection from config (currently hardcoded voice ID)
- Add streaming TTS support (ElevenLabs supports WebSocket streaming)
- Add conversation history for multi-turn interaction

**Performance:**
- TTS writes to temp file then reads back. Use streaming playback to reduce latency
- `sounddevice`/`soundfile` import should fall back to `pygame.mixer` if unavailable

**UX:**
- Voice speed/style configuration
- Integrate as drop-in replacement for OpenAI TTS in AI_Module

---

## voice_commands.py

**UX:**
- "All modules" support ("show everything", "hide all")
- Compound commands ("show weather and hide stocks")
- Brightness/volume commands ("set brightness to 50%")
- State commands ("go to sleep", "activate screensaver")
- Fuzzy matching for module names (handle "whether" -> "weather")

---

## visual_effects.py

**Performance:**
- `create_gradient_surface` iterates pixel-by-pixel. Use `pygame.surfarray` with numpy for 10-100x speedup
- Cache frequently used gradients (same dimensions + colors)

**Visual:**
- Add blur effect using `pygame.transform.smoothscale`
- Add particle system for celebrations (confetti when step goal met)
- Add transition animations (fade, slide) for module show/hide

---

## weather_animations.py

**Visual:**
- Add fog animation (WMO codes 45/48 currently map to "clouds")
- Add wind animation (leaves blowing)
- Add day/night cycle awareness (MoonAnimation at night, SunAnimation during day)

**Bug:**
- `StormAnimation` loads `thunderstorm.png` but the actual file is `thunder_storm.png` (with underscore). Filename mismatch will cause load failure

**Performance:**
- Particle counts are hardcoded (rain: 50, snow: 100). Make configurable based on screen size
