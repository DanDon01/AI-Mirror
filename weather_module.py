import requests
import pygame
import logging
import random
from datetime import datetime, timedelta
from config import (
    CONFIG, FONT_NAME, FONT_SIZE, FONT_SIZE_HERO, COLOR_FONT_DEFAULT,
    COLOR_FONT_BODY, COLOR_PASTEL_RED, COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM,
    COLOR_ACCENT_BLUE, COLOR_ACCENT_AMBER, LINE_SPACING, TRANSPARENCY,
    COLOR_BG_MODULE_ALPHA, COLOR_BG_HEADER_ALPHA, IS_NIGHT,
    load_font,
)
import os
from weather_animations import CloudAnimation, RainAnimation, SunAnimation, StormAnimation, SnowAnimation, MoonAnimation
from visual_effects import VisualEffects
from effects_kit import draw_hero_glow, draw_flare
from config import draw_module_background_fallback
from api_tracker import api_tracker
from background_fetcher import BackgroundFetcher

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
        self._fetcher = BackgroundFetcher("weather")
        self._retry_after = datetime.min  # backoff after a failed fetch
        self._moment_notify = None
        self._prev_animation_kind = None
        self._sunrise_fired_date = None
        self._sunset_fired_date = None
        self._full_moon_fired_date = None
        self._heatwave_notified_at = datetime.min
        self._high_wind_notified_at = datetime.min

        # Show last-good data immediately after a restart (refresh still
        # runs on the first update since last_update stays at datetime.min)
        from data_cache import data_cache
        cached, age = data_cache.load("weather", max_age_sec=86400)
        if cached:
            self.weather_data = cached.get("data")
            self.weather_source = cached.get("source")
            if self.weather_data:
                logger.info(f"Restored cached weather ({int(age / 60)} min old)")

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
            # One request supplies the current display, practical leave-home
            # forecast strip, and real solar timing for the sky animation.
            "hourly": "temperature_2m,precipitation_probability,weather_code,is_day",
            "daily": "sunrise,sunset",
            "forecast_days": 2,
            "timezone": "auto",
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
        hourly = data.get("hourly", {})
        daily = data.get("daily", {})
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
            "hourly": hourly,
            "astronomy": {
                "sunrise": (daily.get("sunrise") or [None])[0],
                "sunset": (daily.get("sunset") or [None])[0],
                "timezone": data.get("timezone", "local"),
            },
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

    def _fetch_weather_blocking(self):
        """Try OpenWeatherMap then Open-Meteo. Runs on a background thread.

        Returns (data, source_name) or raises if both sources fail.
        """
        # Open-Meteo provides current conditions, hourly precipitation and
        # sun data in a single free request. Prefer it even when an older OWM
        # key is configured; OWM remains a robust fallback for outages.
        try:
            data = self._fetch_open_meteo()
            if data:
                return data, "Open-Meteo"
            raise RuntimeError("Open-Meteo returned no data")
        except Exception as exc:
            api_tracker.failure("weather", "open-meteo")
            logger.warning(f"Open-Meteo failed, trying OpenWeatherMap: {exc}")
        if self.api_key:
            try:
                data = self._fetch_openweathermap()
                if data:
                    return data, "OpenWeatherMap"
            except Exception:
                api_tracker.failure("weather", "openweathermap")
                raise
        raise RuntimeError("Open-Meteo unavailable and no OpenWeatherMap fallback configured")

    def update(self):
        # Collect a finished background fetch, if any
        result = self._fetcher.take_result()
        if result is not None:
            ok, value = result
            if ok:
                self.weather_data, self.weather_source = value
                self.update_animation()
                self.last_update = datetime.now()
                from data_cache import data_cache
                data_cache.save("weather", {
                    "data": self.weather_data, "source": self.weather_source,
                })
                logger.info(
                    f"Weather via {self.weather_source} for {self.weather_data['name']}"
                )
            else:
                logger.error(f"Weather fetch failed: {value}")
                self._retry_after = datetime.now() + timedelta(minutes=2)

        current_time = datetime.now()
        if current_time - self.last_update < self.update_interval:
            return
        if current_time < self._retry_after:
            return
        # Kick off a fetch without blocking the render loop
        self._fetcher.submit(self._fetch_weather_blocking)

    def set_moment_callback(self, callback):
        """Register a callback for Director moment triggers (event_director.py)."""
        self._moment_notify = callback

    def update_animation(self):
        try:
            weather_main = self.weather_data['weather'][0]['main'].lower()
            weather_description = self.weather_data['weather'][0]['description'].lower()
            wind = self.weather_data.get('wind', {}).get('speed', 0) or 0
            astronomy = self.astronomy()
            is_night = not astronomy["is_day"]

            if 'clear' in weather_main:
                if is_night:
                    self.animation = MoonAnimation(
                        self.screen_width, self.screen_height, wind_speed=wind,
                        phase=astronomy["moon_phase"], sky_progress=astronomy["moon_progress"])
                else:
                    self.animation = SunAnimation(
                        self.screen_width, self.screen_height, wind_speed=wind,
                        sky_progress=astronomy["sun_progress"])
            elif 'cloud' in weather_main or 'broken' in weather_description:
                partly = 'partly' in weather_description or 'broken' in weather_description
                if is_night and partly:
                    self.animation = MoonAnimation(
                        self.screen_width, self.screen_height, cloudy=True,
                        wind_speed=wind, phase=astronomy["moon_phase"], sky_progress=astronomy["moon_progress"])
                else:
                    self.animation = CloudAnimation(
                        self.screen_width, self.screen_height, partly=partly,
                        wind_speed=wind)
            elif 'rain' in weather_main or 'drizzle' in weather_main:
                heavy = 'heavy' in weather_description
                self.animation = RainAnimation(
                    self.screen_width, self.screen_height, heavy=heavy,
                    wind_speed=wind)
            elif 'thunderstorm' in weather_main:
                self.animation = StormAnimation(
                    self.screen_width, self.screen_height, wind_speed=wind)
            elif 'snow' in weather_main:
                self.animation = SnowAnimation(
                    self.screen_width, self.screen_height, wind_speed=wind)
            else:
                self.animation = None

            if isinstance(self.animation, StormAnimation):
                self.animation.on_flash = self._on_lightning_flash

            self._check_condition_onset(weather_main, is_night, astronomy)
        except Exception as e:
            logging.error(f"Error creating weather animation: {e}")
            self.animation = None

    def _on_lightning_flash(self):
        """Called by StormAnimation on every ambient bolt. Most flashes
        stay ambient -- only occasionally do they earn the full-screen
        Storm Takeover Moment, so it stays a surprise rather than firing
        on every single strike during a storm."""
        if self._moment_notify and random.random() < 0.35:
            self._moment_notify('lightning_strike', None)

    def _check_condition_onset(self, weather_main, is_night, astronomy):
        """Fires a Moment once on the transition INTO a condition, not
        continuously while it holds (e.g. once when rain starts, not
        every frame it keeps raining)."""
        if 'thunderstorm' in weather_main:
            kind = 'storm'
        elif 'rain' in weather_main or 'drizzle' in weather_main:
            kind = 'rain'
        elif 'snow' in weather_main:
            kind = 'snow'
        else:
            kind = weather_main

        if self._moment_notify and kind != self._prev_animation_kind:
            if kind in ('rain', 'storm'):
                self._moment_notify('rain_onset', None)
            elif kind == 'snow':
                self._moment_notify('snow_onset', None)
            elif kind == 'clear' and self._prev_animation_kind in ('rain', 'storm', 'drizzle'):
                self._moment_notify('rain_stopped_sun_out', None)
        self._prev_animation_kind = kind

        if self._moment_notify and is_night:
            phase = astronomy.get('moon_phase', 0)
            near_full = 0.47 <= phase <= 0.53
            today = datetime.now().date()
            if near_full and self._full_moon_fired_date != today:
                self._full_moon_fired_date = today
                self._moment_notify('full_moon_night', None)

    def check_time_based_moments(self):
        """Sunrise/sunset curtain and heatwave/high-wind checks -- run
        every frame from draw() since these are time/data thresholds,
        not condition-class transitions like _check_condition_onset."""
        if not self._moment_notify or not self.weather_data:
            return
        now = datetime.now()
        today = now.date()
        astro = self.astronomy()

        if abs((now - astro['sunrise']).total_seconds()) <= 60 and self._sunrise_fired_date != today:
            self._sunrise_fired_date = today
            self._moment_notify('sunrise', None)
        if abs((now - astro['sunset']).total_seconds()) <= 60 and self._sunset_fired_date != today:
            self._sunset_fired_date = today
            self._moment_notify('sunset', None)

        temp = self.weather_data.get('main', {}).get('temp')
        if isinstance(temp, (int, float)) and temp >= 28 and (now - self._heatwave_notified_at).total_seconds() > 1800:
            self._heatwave_notified_at = now
            self._moment_notify('heatwave', None)

        wind = self.weather_data.get('wind', {}).get('speed', 0) or 0
        if wind >= 12 and (now - self._high_wind_notified_at).total_seconds() > 900:
            self._high_wind_notified_at = now
            self._moment_notify('high_wind', None)

    @staticmethod
    def _parse_weather_time(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _moon_phase(now):
        """0=new, .5=full; sufficient for a graceful long-running sky cue."""
        known_new_moon = datetime(2000, 1, 6, 18, 14)
        return ((now - known_new_moon).total_seconds() / 86400 / 29.53058867) % 1.0

    def astronomy(self, now=None):
        """Solar data plus a continuously changing moon cue for the UI."""
        now = now or datetime.now()
        raw = (self.weather_data or {}).get("astronomy", {})
        sunrise = self._parse_weather_time(raw.get("sunrise"))
        sunset = self._parse_weather_time(raw.get("sunset"))
        if sunrise is None or sunset is None or sunset <= sunrise:
            sunrise = now.replace(hour=6, minute=0, second=0, microsecond=0)
            sunset = now.replace(hour=20, minute=0, second=0, microsecond=0)
        is_day = sunrise <= now < sunset
        day_span = max((sunset - sunrise).total_seconds(), 1)
        sun_progress = min(1.0, max(0.0, (now - sunrise).total_seconds() / day_span))
        # The moon traverses the inverse half of the same celestial arc. It is
        # intentionally atmospheric rather than a false moonrise prediction.
        night_start = sunset if now >= sunset else sunset - timedelta(days=1)
        moon_progress = min(1.0, max(0.0, (now - night_start).total_seconds() / (12 * 3600)))
        phase = self._moon_phase(now)
        return {"sunrise": sunrise, "sunset": sunset, "is_day": is_day,
                "sun_progress": sun_progress, "moon_progress": moon_progress,
                "moon_phase": phase}

    def hourly_timeline(self, slots=5):
        """Next practical three-hourly outlook for the top bar."""
        hourly = (self.weather_data or {}).get("hourly", {})
        times = hourly.get("time") or []
        temperatures = hourly.get("temperature_2m") or []
        rain = hourly.get("precipitation_probability") or []
        codes = hourly.get("weather_code") or []
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        options = []
        for index, stamp in enumerate(times):
            point = self._parse_weather_time(stamp)
            if point is None or point < now or index >= len(temperatures):
                continue
            if point.hour % 3 != 0 and point != now:
                continue
            options.append({"time": point.strftime("%H"), "temp": round(temperatures[index]),
                            "rain": int(rain[index]) if index < len(rain) and rain[index] is not None else 0,
                            "code": int(codes[index]) if index < len(codes) and codes[index] is not None else 0})
            if len(options) >= slots:
                break
        return options

    def get_temperature_color(self, temperature):
        # Ice blue for cold, platinum for temperate, champagne for warm.
        # Keep this restrained rather than turning weather into a warning UI.
        t = float(temperature)
        if t <= 8:
            return COLOR_ACCENT_BLUE
        if t >= 20:
            return COLOR_ACCENT_AMBER
        return COLOR_FONT_DEFAULT

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

            # Paint the atmospheric scene first.  The weather copy and every
            # other module then stay crisp above it, including when rain is
            # travelling down the whole pane of glass.
            if self.animation:
                self.animation.update()
                self.animation.draw(screen)
            self.check_time_based_moments()

            # Title label
            from module_base import ModuleDrawHelper
            draw_y = ModuleDrawHelper.draw_module_title(
                screen, "Weather", x, y, width
            )

            if self.weather_data:
                city_name = self.weather_data['name']
                temp = self.weather_data['main']['temp']
                condition = self.weather_data['weather'][0]['description'].capitalize()
                humidity = self.weather_data['main']['humidity']
                wind_speed = self.weather_data['wind']['speed']
                feels_like = self.weather_data['main']['feels_like']
                cloud_cover = self.weather_data['clouds']['all']

                data_hash = f"{city_name}{temp}{condition}{humidity}{wind_speed}{feels_like}{cloud_cover}"

                # Hero temperature: large, light, platinum
                def _render_hero():
                    font = load_font('regular', FONT_SIZE_HERO)
                    s = font.render(f"{temp:.0f}°", True, self.get_temperature_color(temp))
                    s.set_alpha(TRANSPARENCY)
                    return s

                hero = self._surface_cache.get_or_render(
                    "weather_hero", _render_hero, data_hash
                )
                draw_hero_glow(screen, hero, x, draw_y, self.get_temperature_color(temp),
                               intensity=1.0 if IS_NIGHT else 0.3)
                draw_flare(screen, x, draw_y, hero.get_width(), hero.get_height(),
                          self._surface_cache.flare_alpha("weather_hero"),
                          self.get_temperature_color(temp))
                screen.blit(hero, (x, draw_y))

                # Condition sits beside the hero, baseline-ish aligned
                def _render_cond():
                    s = self.body_font.render(condition, True, COLOR_TEXT_SECONDARY)
                    s.set_alpha(TRANSPARENCY)
                    return s

                cond = self._surface_cache.get_or_render(
                    "weather_cond", _render_cond, data_hash
                )
                screen.blit(
                    cond,
                    (x + hero.get_width() + 14,
                     draw_y + hero.get_height() - cond.get_height() - 10),
                )
                draw_y += hero.get_height() + 6

                # Quiet detail rows
                details = [
                    f"Feels {feels_like:.0f}°   Humidity {humidity}%",
                    f"Wind {wind_speed:.1f} m/s   Cloud {cloud_cover}%",
                    city_name,
                ]
                for i, text in enumerate(details):
                    if draw_y > y + height - 22:
                        break

                    def _render(t=text, last=(i == len(details) - 1)):
                        s = self.small_font.render(
                            t, True, COLOR_TEXT_DIM if last else COLOR_TEXT_SECONDARY
                        )
                        s.set_alpha(TRANSPARENCY)
                        return s

                    surf = self._surface_cache.get_or_render(
                        f"weather_detail_{i}", _render, data_hash
                    )
                    screen.blit(surf, (x, draw_y))
                    draw_y += 24

            else:
                err = self.body_font.render("Weather unavailable", True, COLOR_PASTEL_RED)
                err.set_alpha(TRANSPARENCY)
                screen.blit(err, (x, draw_y))
        except Exception as e:
            logging.error(f"Error drawing weather module: {e}")

    def cleanup(self):
        pass
