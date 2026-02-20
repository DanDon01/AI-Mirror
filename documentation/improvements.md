# AI-Mirror: Overall Improvement Suggestions

Architecture, code quality, deployment, UX, and performance improvements.

---

## Architecture

### 1. Module Base Class
Create an abstract base class `MirrorModule` that enforces the interface contract:
```python
from abc import ABC, abstractmethod

class MirrorModule(ABC):
    @abstractmethod
    def update(self): ...
    @abstractmethod
    def draw(self, screen, position): ...
    @abstractmethod
    def cleanup(self): ...
```
Currently all modules implement this informally but inconsistently (`elevenvoice_module` lacks `draw`/`cleanup`, `smarthome_module` only accepts tuple positions). A base class makes violations obvious at import time.

### 2. Event Bus / Inter-Module Communication
Modules cannot currently share data. Add a simple pub/sub event bus:
- Weather module publishes sunrise/sunset -> Clock module displays it
- Calendar module publishes "event starting in 5 min" -> Voice module announces it
- Fitbit module publishes "goal achieved" -> Retro screensaver does celebration animation
- Voice module publishes "show weather" -> Module manager handles visibility

Implementation: a simple `EventBus` class with `subscribe(event_name, callback)` and `publish(event_name, data)`. Inject into all modules at init.

### 3. Configuration Overhaul
The `CONFIG` dict in `config.py` currently mixes module configs, screen settings, layout constants, and styling. Split into:
- `config/settings.yaml` -- user-editable settings (city, tickers, API preferences)
- `config/defaults.py` -- code constants (colors, font sizes, default dimensions)
- `config/secrets.py` -- env var loading only (keeps secret access in one place)

Benefits: users can edit a YAML file instead of Python code, and secrets are isolated.

### 4. Thread Safety
The `module_visibility` dict and `CONFIG` dict are shared across threads without locks. The `ai_voice_module` runs WebSocket handlers in daemon threads that modify state read by the main Pygame loop. Critical shared state needs `threading.Lock` guards:
- `module_visibility` dict
- Module status fields (`self.status`, `self.recording`, `self.processing`)
- `response_queue` (already using `Queue`, which is thread-safe)

### 5. State Machine Formalisation
Mirror states (active/screensaver/sleep) are managed with string comparison. Implement a proper state machine with:
- Defined transitions (active -> screensaver only via timeout or key press)
- Entry/exit actions (e.g., pause data fetching in sleep mode)
- Configurable timeouts (screensaver after 5 min idle, sleep after 30 min)
- Event-driven transitions (PIR sensor triggers wake from sleep)

---

## Code Quality

### 1. Remove Dead Code
- `stocks_module.py` has two update methods (`update()` and `update_data()`) that appear to be duplicates
- `AI_Module.py` has multiple audio initialization paths that overlap
- Several modules have commented-out code blocks

### 2. Consistent Position Handling
Some modules accept position as `(x, y)` tuple, others as `{'x': int, 'y': int}` dict. The main loop converts dict to tuple for some modules. Standardise on dict format everywhere since it carries width/height info.

### 3. Specific Exception Handling
Most modules catch broad `Exception` and log it. Add specific exception types and recovery strategies:
- API rate limit -> exponential backoff -> cached data -> error display
- Network timeout -> retry with backoff -> show stale data with warning
- Auth failure -> token refresh -> re-auth prompt

### 4. Type Hints
Add type annotations to all public methods. Use `typing.Protocol` for the module interface so type checkers can verify module implementations without requiring inheritance.

### 5. Linting and Formatting
Add `pyproject.toml` with `ruff` configuration:
- Enforce consistent naming (currently mix of `AI_Module.py` vs `ai_voice_module.py`)
- Enforce consistent class naming (`ClockModule` vs `ElevenVoice`)
- Auto-format on save in VSCode

---

## Deployment

### 1. systemd Service
Create `mirror.service` for automatic startup on boot:
```ini
[Unit]
Description=AI-Mirror Smart Mirror
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=dan
WorkingDirectory=/home/dan/Projects/AI-Mirror
ExecStart=/usr/bin/python3 AI-Mirror.py
Restart=on-failure
RestartSec=10
WatchdogSec=300

[Install]
WantedBy=multi-user.target
```
Benefits: auto-restart on crash, boot-time startup, proper logging to journalctl.

### 2. OTA Updates
Add update mechanism triggered by voice command or scheduled cron:
```bash
cd /home/dan/Projects/AI-Mirror
git pull origin main
pip install -r requirements.txt
sudo systemctl restart mirror
```
Wrap in a script with pre-update backup, dependency check, and rollback on failure.

### 3. Health Monitoring
Add a `/health` HTTP endpoint (simple Flask or aiohttp on a background thread) that reports:
- Module status (which are running, which have errors)
- Uptime and last restart time
- Last API call timestamps per module
- Error counts and last error messages
- System metrics (CPU, memory, temperature)

Accessible from phone on local network for remote monitoring.

### 4. Install Script
Create `setup.sh` for fresh Pi deployment:
```bash
#!/bin/bash
# Install system dependencies
sudo apt-get install -y python3-pip python3-venv portaudio19-dev ...
# Create virtual environment
python3 -m venv venv
source venv/bin/activate
# Install Python packages
pip install -r requirements.txt
# Set up systemd service
sudo cp mirror.service /etc/systemd/system/
sudo systemctl enable mirror
```

### 5. Backup/Restore
Token refresh operations write directly to `Variables.env`. Add backup before write and a restore mechanism. Also backup the env file before OTA updates.

---

## UX

### 1. Presence Detection
Add PIR sensor via GPIO (`gpiod` is already in requirements.txt) for auto wake/sleep:
- PIR detects motion -> wake from sleep to active state
- No motion for 5 minutes -> switch to screensaver
- No motion for 30 minutes -> switch to sleep (clock only)

Alternatively, use a USB camera with basic motion detection (OpenCV `BackgroundSubtractor`).

### 2. Brightness Control
Auto-adjust display brightness based on:
- Ambient light sensor on GPIO (e.g., BH1750 via I2C)
- Time-of-day schedule (dim at night, bright during day)
- Manual voice command ("set brightness to 50%")

Use `xrandr --output HDMI-1 --brightness 0.5` or `/sys/class/backlight/` on Pi.

### 3. Onboarding Wizard
First-run setup that walks through:
1. Display calibration (resolution, orientation)
2. API key entry (guided setup for each service)
3. Audio test (mic recording + speaker playback)
4. Module selection (which modules to enable)
5. City/location configuration

### 4. Remote Configuration
Web UI accessible from phone on local network:
- Change settings (city, tickers, modules) without SSH
- View module status and error logs
- Trigger manual data refresh
- Upload custom screensaver images

---

## Performance

### 1. Lazy Module Loading
Only import and initialise modules that are enabled in `module_visibility` config. Currently all modules are imported at the top of `AI-Mirror.py` regardless of whether they are enabled. Lazy imports reduce startup time and memory.

### 2. Surface Caching
Cache rendered text surfaces and module backgrounds that do not change every frame:
- Clock: only re-render when the second changes
- Weather: only re-render when data refreshes (every 30 min)
- Stocks: only re-render when data refreshes
- Module backgrounds: render once and reuse

Estimated frame time reduction: 30-50% on Pi 5.

### 3. Separate Update Timers
The current approach calls `update()` every frame (30 FPS) and each module internally throttles. Instead, use separate timers in the main loop:
```python
if time.time() - weather_last_update > 1800:
    modules['weather'].update()
    weather_last_update = time.time()
```
This avoids the overhead of each module checking its own timer 30 times per second.

### 4. Memory Monitoring
The Pi 5 has 8GB but long-running Pygame apps can leak surfaces. Add periodic (every 5 minutes) memory usage logging:
```python
import psutil
process = psutil.Process()
logger.info(f"Memory: {process.memory_info().rss / 1024 / 1024:.0f} MB")
```
Alert if memory exceeds a threshold (e.g., 500 MB).
