# AI-Mirror Test Suite

Standalone test scripts for validating the AI-Mirror project on a Raspberry Pi 5.

## Prerequisites

- Raspberry Pi 5 with Raspberry Pi OS
- USB microphone connected (for audio input tests)
- Monitor with speakers (for audio output and display tests)
- `Variables.env` populated in the parent directory (for API tests)
- All Python dependencies installed: `pip install -r requirements.txt`

## Running Tests

### Run everything
```bash
python tests/run_all_tests.py --all
```

### Run by category
```bash
python tests/run_all_tests.py --api-only      # API connectivity (network required)
python tests/run_all_tests.py --audio-only     # Mic + speaker hardware
python tests/run_all_tests.py --display-only   # Pygame module rendering
python tests/run_all_tests.py --logic-only     # Pure logic, no hardware/API
```

### Run individual tests
```bash
python tests/test_env_keys.py          # Check all env vars are set
python tests/test_openai_api.py        # OpenAI API: models, chat, TTS
python tests/test_openmeteo_api.py     # Open-Meteo (no key needed)
python tests/test_audio_input.py       # USB mic recording
python tests/test_audio_output.py      # Speaker playback
python tests/test_clock_display.py     # Clock module in window
python tests/test_voice_commands.py    # Command parser logic
python tests/test_integration.py       # Full module init + screenshot
```

## Test Categories

### API Tests (network required, no display)
| Script | Tests | API Key Required |
|--------|-------|-----------------|
| `test_env_keys.py` | All 12 environment variables are set | N/A |
| `test_openai_api.py` | Model list, chat completion, TTS | OPENAI_API_KEY |
| `test_openweathermap_api.py` | Weather fetch for Birmingham,UK | OPENWEATHERMAP_API_KEY |
| `test_openmeteo_api.py` | Geocoding + weather (free) | None |
| `test_google_calendar_api.py` | OAuth2 refresh, event listing | GOOGLE_* keys |
| `test_fitbit_api.py` | OAuth2 refresh, activity fetch | FITBIT_* keys |
| `test_elevenlabs_api.py` | Voice list, TTS synthesis | ELEVENLABS_API_KEY |
| `test_yfinance_api.py` | Stock data for 8 tickers | None |

### Hardware Tests (Pi-specific)
| Script | Tests | Hardware |
|--------|-------|----------|
| `test_audio_input.py` | arecord device list, 2s recording, energy level | USB microphone |
| `test_audio_output.py` | mixer init, sine tone, sound effect, gTTS playback | Speakers |

### Display Tests (opens a pygame window)
| Script | Duration | What You See |
|--------|----------|-------------|
| `test_clock_display.py` | 5 sec | Scrolling clock and date |
| `test_weather_display.py` | 5 sec | Weather data with styling |
| `test_stocks_display.py` | 5 sec | Stock ticker grid |
| `test_calendar_display.py` | 5 sec | Calendar events list |
| `test_fitbit_display.py` | 5 sec | Fitbit health metrics |
| `test_retro_display.py` | 5 sec | Falling retro icons |
| `test_weather_animations.py` | 30 sec | All 6 animation types cycling |
| `test_visual_effects.py` | 5 sec | Rounded rects, gradients, pulses |

### Logic Tests (no hardware, no API)
| Script | Tests |
|--------|-------|
| `test_voice_commands.py` | 11 voice command phrases with expected parse results |

### Integration Test
| Script | Tests |
|--------|-------|
| `test_integration.py` | Init all modules, layout calc, one draw frame, saves screenshot |

## Expected Output

Each test prints PASS/FAIL for individual checks and a summary at the end:
```
Testing OpenAI API...
--------------------------------------------------
  [PASS] API key present -- key present (51 chars)
  [PASS] Model list -- 42 models listed, gpt-4o=found
  [PASS] Chat completion (gpt-4o) -- response: 'test ok'
  [PASS] TTS endpoint (gpt-4o-mini-tts) -- TTS audio: 4523 bytes
  [PASS] Realtime model available -- realtime model found

==================================================
  Results: 5/5 passed, 0 failed
==================================================
```

Exit code 0 = all passed, non-zero = failures.

## Troubleshooting

**"Variables.env not found"**
- Ensure `Variables.env` exists in the parent directory of the project (one level up from `AI-Mirror/`)

**"OPENWEATHERMAP_API_KEY not set"**
- Check that the key name in Variables.env matches exactly (no typos, no extra spaces)

**"arecord not found"**
- Audio input tests require Linux/ALSA. These will fail on Windows/macOS (expected).

**"token expired"**
- Fitbit and Google Calendar tokens expire. Run the token refresh test first, then update Variables.env with the new tokens.

**Display tests show black window**
- The module may have failed to fetch data. Check the console output for API errors before the window opens.

**"pygame.error: No available video device"**
- Ensure you're running on the Pi with a display connected, or use `export DISPLAY=:0` for remote SSH sessions.

**yfinance rate limiting**
- Yahoo Finance aggressively rate-limits. If test_yfinance fails, wait 30 minutes and retry.
