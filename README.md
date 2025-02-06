AI-Mirror

AI-Mirror is a smart mirror project built using a Raspberry Pi 5, designed to display useful information and interact with users through gesture control and voice commands.

Features

Display of current time and date
Weather information
Fitbit data integration
Stock market updates
Package tracking
Gesture control for interface navigation
Text-to-speech notifications

Hardware Requirements

Raspberry Pi 5
Monitor (preferably with built-in speakers for audio output)
Two-way mirror or acrylic sheet
Pi Camera module (for gesture control)
Power supply
Frame for mounting

Software Dependencies

Python 3.x
Pygame
OpenCV
pyttsx3
Fitbit API
(Add other libraries as you implement features)

Installation

Clone this repository:
Copygit clone https://github.com/DanDon01/AI-Mirror.git

Navigate to the project directory:
Copycd AI-Mirror

Install required Python packages:
Copypip install -r requirements.txt

Setup environment variables:
Create a file named Variables.env in the project directory and add your environment variables in the following format:

VARIABLE_NAME=value

Fitbit API Credentials
FITBIT_CLIENT_ID=your_fitbit_client_id FITBIT_CLIENT_SECRET=your_fitbit_client_secret FITBIT_ACCESS_TOKEN=your_fitbit_access_token FITBIT_REFRESH_TOKEN=your_fitbit_refresh_token

Google Calendar API Credentials
GOOGLE_CLIENT_ID=your_google_client_id GOOGLE_CLIENT_SECRET=your_google_client_secret GOOGLE_ACCESS_TOKEN=your_google_access_token GOOGLE_REFRESH_TOKEN=your_google_refresh_token

OpenWeatherMap API Key
OPENWEATHERMAP_API_KEY=your_openweathermap_api_key

OpenAI API Key
OPENAI_API_KEY=your_openai_api_key

To obtain the necessary credentials:

1. Fitbit API:
   - Go to https://dev.fitbit.com/
   - Create a new application
   - Use OAuth 2.0 flow to get access and refresh tokens

2. Google Calendar API:
   - Visit Google Cloud Console
   - Create a new project
   - Enable Calendar API
   - Create OAuth 2.0 credentials
   - Complete OAuth flow to get tokens

3. OpenWeatherMap:
   - Register at https://openweathermap.org/api
   - Get your API key from your account

4. OpenAI:
   - Sign up at https://platform.openai.com/
   - Get your API key from account settings

Usage

Configure your API keys and tokens in a config.py file (see config_example.py for template).
Run the main script:
Copypython magic_mirror.py

Project Structure

magic_mirror.py: Main script that runs the mirror interface
fitbit_module.py: Module for Fitbit data integration
stocks_module.py: Module for stock market updates
weather_module.py: Module for weather information
package_tracking_module.py: Module for package tracking
gesture_control.py: Module for gesture recognition
config.py: Configuration file for API keys and settings

Contributing
Contributions to AI-Mirror are welcome! Please feel free to submit a Pull Request.
License
This project is licensed under the MIT License - see the LICENSE.md file for details.
Acknowledgments

Fitbit for their API
OpenWeatherMap for weather data
