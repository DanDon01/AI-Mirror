# AI-Mirror

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.x-green.svg)
![Status](https://img.shields.io/badge/status-in%20development-yellow)
[![Made with RPi](https://img.shields.io/badge/Made%20with-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org)

> Transform any monitor into an interactive AI-powered smart mirror! This project combines a Raspberry Pi 5 mounted behind a portrait-oriented display, covered with two-way mirror acrylic and framed to create a seamless mirror appearance. Interact with your AI assistant through voice commands while getting real-time information about your day.

## Key Features

- **Smart Display**
  - Real-time clock and calendar
  - Local weather updates with animated effects
  - Fitbit health data integration (steps, calories, sleep, heart rate)
  - Stock market ticker with visual alerts (US and UK markets)

- **AI Voice Interaction**
  - Dual AI system with OpenAI Realtime API and standard GPT-4 fallback
  - ElevenLabs premium text-to-speech integration
  - Automatic fallback between AI systems
  - Natural language interactions
  - Voice command parsing for module control ("show weather", "hide stocks")

- **Visual Experience**
  - Modern UI with rounded corners and subtle shadows
  - Animated transitions and fade effects
  - Pulsing highlights for important information
  - Dynamic color coding for data
  - Retro character screensaver with 27 pop culture icons
  - Responsive layout for multiple screen sizes (21", 24", 27")

- **Application States**
  - Active: All modules visible, voice ready
  - Screensaver: Retro character animation
  - Sleep: Clock only (minimal power)

## Planned / In Development

- Gesture recognition or PIR-based presence detection for hands-free wake/sleep
- Camera-based interaction and face detection
- Smart home integration (Home Assistant / MQTT)
- Local AI model support via Ollama over network
- Realtime avatar interaction

## Hardware Requirements

- Raspberry Pi 5 (8GB RAM recommended)
- 24" Monitor or larger (portrait orientation, built-in speakers)
- Two-way mirror acrylic sheet
- USB Microphone with good pickup range
- 5V/4A Power Supply
- Custom frame for mounting

## Software Dependencies

```
Python 3.x
Pygame
OpenAI API
SpeechRecognition
gTTS (Google Text-to-Speech)
ElevenLabs API (optional, premium TTS)
WebSocket-client
FitbitAPI
yfinance
Google Calendar API
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

Create `Variables.env` in the parent directory with your API keys:
```bash
# OpenAI API
OPENAI_API_KEY=your_key

# Weather API
OPENWEATHERMAP_API_KEY=your_key

# Fitbit API
FITBIT_CLIENT_ID=your_id
FITBIT_CLIENT_SECRET=your_secret
FITBIT_ACCESS_TOKEN=your_token
FITBIT_REFRESH_TOKEN=your_refresh_token

# Google Calendar API
GOOGLE_CLIENT_ID=your_id
GOOGLE_CLIENT_SECRET=your_secret
GOOGLE_ACCESS_TOKEN=your_token
GOOGLE_REFRESH_TOKEN=your_refresh_token

# ElevenLabs API (optional)
ELEVENLABS_API_KEY=your_key
ELEVENLABS_VOICE_ID=your_voice_id
```

4. **Run the application:**
```bash
python AI-Mirror.py
```

## Controls

| Key | Action |
|-----|--------|
| `Space` | Trigger voice interaction |
| `s` | Cycle state: active -> screensaver -> sleep |
| `d` | Toggle debug mode |
| `q` | Quit |

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

- OpenAI for GPT-4 and Realtime API capabilities
- ElevenLabs for premium text-to-speech
- Fitbit for their comprehensive API
- OpenWeatherMap for reliable weather data
- The Raspberry Pi Foundation
- Contributors and the open-source community

---
<div align="center">
Made by DanDon01
</div>
