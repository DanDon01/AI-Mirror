import requests
import pygame
import logging
from datetime import datetime, timedelta
from config import CONFIG, FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_FONT_BODY, COLOR_PASTEL_RED, LINE_SPACING, TRANSPARENCY, COLOR_BG_MODULE_ALPHA, COLOR_BG_HEADER_ALPHA
import os
from weather_animations import CloudAnimation, RainAnimation, SunAnimation, StormAnimation, SnowAnimation, MoonAnimation
from visual_effects import VisualEffects
from config import draw_module_background_fallback
from api_tracker import api_tracker

logger = logging.getLogger("WeatherModule")

# WMO Weather interpretation codes (used by Open-Meteo)
WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


class WeatherModule:
    def __init__(self, api_key, city, screen_width=800, screen_height=600, icons_path=None):
        self.api_key = api_key
        self.city = city
        self.weather_data = None
        self.font = None
        self.last_update = datetime.min
        self.update_interval = timedelta(minutes=30)
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.animation = None
        self.icons_path = icons_path
        self.effects = VisualEffects()
        self._geo_cache = None  # Cache lat/lon for Open-Meteo
        self.weather_source = None  # Track which API provided data
        from module_base import SurfaceCache
        self._surface_cache = SurfaceCache()
        self._last_data_hash = None

    def _geocode_city(self):
        """Convert city name to lat/lon using Open-Meteo geocoding API."""
        if self._geo_cache:
            return self._geo_cache

        city_name = self.city.split(",")[0].strip()
        country = self.city.split(",")[1].strip() if "," in self.city else None

        try:
            url = "https://geocoding-api.open-meteo.com/v1/search"
            params = {"name": city_name, "count": 5, "format": "json"}
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if not results:
                logger.warning(f"Geocoding returned no results for '{self.city}'")
                return None

            # Try to match country code if provided
            if country:
                for r in results:
                    if r.get("country_code", "").upper() == country.upper():
                        self._geo_cache = {
                            "lat": r["latitude"],
                            "lon": r["longitude"],
                            "name": r.get("name", city_name),
                            "country": r.get("country_code", country),
                        }
                        return self._geo_cache

            # Fall back to first result
            r = results[0]
            self._geo_cache = {
                "lat": r["latitude"],
                "lon": r["longitude"],
                "name": r.get("name", city_name),
                "country": r.get("country_code", ""),
            }
            return self._geo_cache

        except Exception as e:
            logger.error(f"Geocoding failed for '{self.city}': {e}")
            return None

    def _wmo_to_main(self, code):
        """Map WMO weather code to a simple category for animations."""
        if code <= 1:
            return "clear"
        if code <= 3:
            return "clouds"
        if code in (45, 48):
            return "clouds"
        if code in range(51, 68):
            return "rain"
        if code in range(71, 78) or code in (85, 86):
            return "snow"
        if code >= 95:
            return "thunderstorm"
        if code in range(80, 83):
            return "rain"
        return "clouds"

    def _fetch_open_meteo(self):
        """Fetch current weather from Open-Meteo (no API key needed)."""
        if not api_tracker.allow("weather", "open-meteo"):
            return None
        geo = self._geocode_city()
        if not geo:
            return None

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": geo["lat"],
            "longitude": geo["lon"],
            "current": ",".join([
                "temperature_2m", "relative_humidity_2m", "apparent_temperature",
                "weather_code", "wind_speed_10m", "pressure_msl", "cloud_cover",
            ]),
            "wind_speed_unit": "ms",
        }

        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        api_tracker.record("weather", "open-meteo")
        data = resp.json()
        current = data.get("current", {})

        wmo_code = current.get("weather_code", 0)
        description = WMO_CODES.get(wmo_code, "Unknown")
        main_condition = self._wmo_to_main(wmo_code)

        # Normalise to the same dict shape the draw() method expects
        return {
            "name": geo["name"],
            "sys": {"country": geo["country"]},
            "main": {
                "temp": current.get("temperature_2m", 0),
                "feels_like": current.get("apparent_temperature", 0),
                "humidity": current.get("relative_humidity_2m", 0),
                "pressure": current.get("pressure_msl", 0),
            },
            "weather": [{"main": main_condition, "description": description}],
            "wind": {"speed": current.get("wind_speed_10m", 0)},
            "clouds": {"all": current.get("cloud_cover", 0)},
        }

    def _fetch_openweathermap(self):
        """Fetch current weather from OpenWeatherMap (requires API key)."""
        if not api_tracker.allow("weather", "openweathermap"):
            return None
        url = f"http://api.openweathermap.org/data/2.5/weather?q={self.city}&appid={self.api_key}&units=metric"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        api_tracker.record("weather", "openweathermap")
        return resp.json()

    def update(self):
        current_time = datetime.now()
        if current_time - self.last_update < self.update_interval:
            if not hasattr(self, 'last_skip_log') or current_time.timestamp() - self.last_skip_log > 60:
                logging.debug("Skipping weather update: Not enough time has passed since last update")
                self.last_skip_log = current_time.timestamp()
            return

        # Try OpenWeatherMap first (if key exists), then Open-Meteo as fallback
        fetched = False

        if self.api_key:
            try:
                self.weather_data = self._fetch_openweathermap()
                self.weather_source = "OpenWeatherMap"
                fetched = True
                logger.info(f"Weather via OpenWeatherMap for {self.weather_data['name']}")
            except Exception as e:
                logger.warning(f"OpenWeatherMap failed, trying Open-Meteo: {e}")

        if not fetched:
            try:
                self.weather_data = self._fetch_open_meteo()
                if self.weather_data:
                    self.weather_source = "Open-Meteo"
                    fetched = True
                    logger.info(f"Weather via Open-Meteo for {self.weather_data['name']}")
                else:
                    logger.error("Open-Meteo returned no data")
            except Exception as e:
                logger.error(f"Open-Meteo also failed: {e}")

        if fetched:
            self.update_animation()
            self.last_update = current_time
        else:
            self.weather_data = None
            self.animation = None

    def update_animation(self):
        try:
            weather_main = self.weather_data['weather'][0]['main'].lower()
            weather_description = self.weather_data['weather'][0]['description'].lower()

            if 'clear' in weather_main:
                self.animation = SunAnimation(self.screen_width, self.screen_height)
            elif 'cloud' in weather_main or 'broken' in weather_description:
                partly = 'partly' in weather_description or 'broken' in weather_description
                self.animation = CloudAnimation(self.screen_width, self.screen_height, partly=partly)
            elif 'rain' in weather_main:
                heavy = 'heavy' in weather_description
                self.animation = RainAnimation(self.screen_width, self.screen_height, heavy=heavy)
            elif 'thunderstorm' in weather_main:
                self.animation = StormAnimation(self.screen_width, self.screen_height)
            elif 'snow' in weather_main:
                self.animation = SnowAnimation(self.screen_width, self.screen_height)
            else:
                self.animation = None
        except Exception as e:
            logging.error(f"Error creating weather animation: {e}")
            self.animation = None

    def get_temperature_color(self, temperature):
        # Clamp temperature between 0 and 32
        t = max(0, min(temperature, 32))
        
        if t <= 15:
            # White (255, 255, 255) to Blue (0, 0, 255)
            ratio = t / 15
            r = int(255 * (1 - ratio))
            g = int(255 * (1 - ratio))
            b = 255
        elif t <= 21:
            # Blue (0, 0, 255) to Yellow (255, 255, 0)
            ratio = (t - 15) / 6
            r = int(255 * ratio)
            g = int(255 * ratio)
            b = int(255 * (1 - ratio))
        else:
            # Yellow (255, 255, 0) to Red (255, 0, 0)
            ratio = (t - 21) / 11
            r = 255
            g = int(255 * (1 - ratio))
            b = 0
        
        return (r, g, b)

    def draw(self, screen, position):
        """Draw weather module -- no background, floating text on black."""
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 300)
            else:
                x, y = position
                width, height = 300, 300

            styling = CONFIG.get('module_styling', {})
            fonts = styling.get('fonts', {})
            padding = styling.get('spacing', {}).get('padding', 12)
            line_height = styling.get('spacing', {}).get('line_height', 28)

            if not hasattr(self, 'title_font') or self.title_font is None:
                from module_base import ModuleDrawHelper
                title_f, body_f, small_f = ModuleDrawHelper.get_fonts()
                self.title_font = title_f
                self.body_font = body_f
                self.small_font = small_f

            if self.font is None:
                self.font = self.body_font

            # Title label
            from module_base import ModuleDrawHelper
            draw_y = ModuleDrawHelper.draw_module_title(
                screen, "Weather", x, y, width
            )

            if self.weather_data:
                city_name = self.weather_data['name']
                country_code = self.weather_data['sys']['country']
                temp = self.weather_data['main']['temp']
                condition = self.weather_data['weather'][0]['description'].capitalize()
                humidity = self.weather_data['main']['humidity']
                wind_speed = self.weather_data['wind']['speed']
                feels_like = self.weather_data['main']['feels_like']
                cloud_cover = self.weather_data['clouds']['all']

                data_hash = f"{city_name}{temp}{condition}{humidity}{wind_speed}{feels_like}{cloud_cover}"

                lines = [
                    (f"{city_name}, {country_code}", COLOR_FONT_DEFAULT),
                    (f"{temp:.1f}C  {condition}", self.get_temperature_color(temp)),
                    (f"Feels {feels_like:.1f}C", self.get_temperature_color(feels_like)),
                    (f"Humidity {humidity}%", COLOR_FONT_BODY),
                    (f"Wind {wind_speed} m/s", COLOR_FONT_BODY),
                    (f"Clouds {cloud_cover}%", COLOR_FONT_BODY),
                ]

                for i, (text, color) in enumerate(lines):
                    if draw_y > y + height - line_height:
                        break

                    def _render(t=text, c=color):
                        s = self.body_font.render(t, True, c)
                        s.set_alpha(TRANSPARENCY)
                        return s

                    surf = self._surface_cache.get_or_render(
                        f"weather_line_{i}", _render, data_hash
                    )
                    screen.blit(surf, (x, draw_y))
                    draw_y += line_height

                # Weather animation across full screen (clouds, sun, rain, etc.)
                if self.animation:
                    self.animation.update()
                    self.animation.draw(screen)
            else:
                err = self.body_font.render("Weather unavailable", True, COLOR_PASTEL_RED)
                err.set_alpha(TRANSPARENCY)
                screen.blit(err, (x, draw_y))
        except Exception as e:
            logging.error(f"Error drawing weather module: {e}")

    def cleanup(self):
        pass
