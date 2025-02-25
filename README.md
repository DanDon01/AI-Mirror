# AI-Mirror 🪞

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.x-green.svg)
![Status](https://img.shields.io/badge/status-in%20development-yellow)
[![Made with RPi](https://img.shields.io/badge/Made%20with-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org)

> Transform any monitor into an interactive AI-powered smart mirror! This project combines a Raspberry Pi 5 mounted behind a portrait-oriented display, covered with two-way mirror acrylic and framed to create a seamless mirror appearance. Interact with your AI assistant through voice commands while getting real-time information about your day - all while looking like a normal mirror on your wall!

## ✨ Key Features

- 🕒 **Smart Display**
  - Real-time clock and calendar
  - Local weather updates and forecasts
  - Fitbit health data integration
  - Stock market ticker with visual alerts
  - Package delivery tracking
  
- 🤖 **Advanced AI Integration**
  - Dual AI system with OpenAI GPT-4 and Realtime API
  - Automatic fallback between AI systems
  - "Mirror" hotword activation
  - Natural language interactions
  - Personalized responses
  
- 👋 **Interactive Controls**
  - Voice-activated commands
  - Gesture recognition for hands-free control
  - Customizable interface layout
  - Motion detection for power saving

- 🏠 **Smart Home Integration**
  - Compatible with major smart home platforms
  - Control lights, thermostats, and other IoT devices
  - Scene automation support
  - Status monitoring

- 🎨 **Enhanced Visual Experience**
  - Sleek, modern UI with rounded corners
  - Subtle animations and transitions
  - Text shadows for improved readability on mirror
  - Dynamic color coding for information
  - Responsive layout for different screen sizes

## 🔧 Installation Overview

1. **Hardware Assembly**
   - Mount the monitor in portrait orientation
   - Attach Raspberry Pi 5 to back of monitor
   - Connect USB microphone for voice input
   - Apply two-way mirror acrylic sheet to monitor surface
   - Install custom frame around assembly
   - Mount final assembly on wall with appropriate anchors

2. **Mirror Setup**
   - Position at eye level for optimal interaction
   - Ensure proper ventilation around Pi
   - Route power cables through wall (optional)
   - Connect to home WiFi network
   - Calibrate microphone and camera positions

## 🛠️ Hardware Requirements

- Raspberry Pi 5 (8GB RAM recommended)
- 24" Monitor or larger (with built-in speakers)
- Two-way mirror or acrylic sheet with mirror film
- Raspberry Pi Camera Module v3
- USB Microphone with good pickup range
- 5V/4A Power Supply
- Custom frame for mounting

## 📦 Software Dependencies

```bash
Python 3.x
Pygame
OpenCV-Python
SpeechRecognition
gTTS (Google Text-to-Speech)
OpenAI API
Websockets
FitbitAPI
yfinance
```

## 🚀 Quick Start

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
Create `Variables.env` with your API keys:
```bash
# Fitbit API
FITBIT_CLIENT_ID=your_id
FITBIT_CLIENT_SECRET=your_secret
FITBIT_ACCESS_TOKEN=your_token
FITBIT_REFRESH_TOKEN=your_refresh_token

# Weather API
OPENWEATHERMAP_API_KEY=your_key

# OpenAI API
OPENAI_API_KEY=your_key

# Google Calendar API
GOOGLE_CLIENT_ID=your_id
GOOGLE_CLIENT_SECRET=your_secret
GOOGLE_ACCESS_TOKEN=your_token
GOOGLE_REFRESH_TOKEN=your_refresh_token
```

4. **Run the application:**
```bash
python AI-Mirror.py
```

## 🎯 Core Functionalities

### Dual AI Assistant System
- Primary system using OpenAI's Realtime API for faster responses
- Fallback system using standard GPT-4 API for reliability
- Automatic switching between systems based on availability
- Voice activation with "Mirror" hotword
- Natural language processing for conversational interaction

### Enhanced Visual Display
- Modern UI with rounded corners and subtle shadows
- Animated transitions and fade effects
- Pulsing highlights for important information
- Progress bars for visual data representation
- Color-coded information for quick understanding

### Smart Display Modules
- Modular widget system for customizable layouts
- Automatic brightness adjustment based on ambient light
- Energy-efficient screen management with sleep mode
- Screensaver mode with retro character animations
- Smooth transitions between display states

### Data Integration
- Real-time weather updates and forecasts
- Calendar synchronization with visual event grouping
- Health metrics visualization with progress tracking
- Stock market data with visual alerts for significant changes
- Package delivery status tracking

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE.md) file for details.

## 🙏 Acknowledgments

- Fitbit for their comprehensive API
- OpenWeatherMap for reliable weather data
- OpenAI for GPT-4 and Realtime API capabilities
- The Raspberry Pi Foundation
- Contributors and the open-source community

---
<div align="center">
Made with ❤️ by DanDon01
</div>
