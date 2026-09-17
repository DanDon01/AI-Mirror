import requests
import pygame
import logging
import math
import random
from datetime import datetime, timedelta
from config import (
    CONFIG, FONT_NAME, FONT_SIZE, FONT_SIZE_HERO, COLOR_FONT_DEFAULT,
    COLOR_FONT_BODY, COLOR_PASTEL_RED, COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM,
    COLOR_ACCENT_BLUE, COLOR_ACCENT_AMBER, COLOR_ACCENT_GREEN, COLOR_ACCENT_RED,
    LINE_SPACING, TRANSPARENCY,
    COLOR_BG_MODULE_ALPHA, COLOR_BG_HEADER_ALPHA, IS_NIGHT,
    load_font,
)
import os
from weather_animations import CloudAnimation, RainAnimation, SunAnimation, StormAnimation, SnowAnimation, MoonAnimation
from visual_effects import VisualEffects
from effects_kit import draw_hero_glow, draw_flare, glow_sprite
from module_base import InstrumentPanel
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


class WeatherModule(InstrumentPanel):
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
                "weather_code", "wind_speed_10m", "wind_direction_10m",
                "pressure_msl", "cloud_cover",
            ]),
            # One request supplies the current display, the forecast curve,
            # the multi-day outlook, and real solar timing for the sky
            # animation. Visibility and UV are hourly-only on this API.
            "hourly": ",".join([
                "temperature_2m", "precipitation_probability", "weather_code",
                "is_day", "visibility", "uv_index",
            ]),
            "daily": ",".join([
                "sunrise", "sunset", "temperature_2m_max", "temperature_2m_min",
                "weather_code",
            ]),
            "forecast_days": 5,
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

        # Visibility and UV are hourly-only, so read the slot covering now.
        now_index = self._current_hour_index(hourly.get("time") or [])
        visibility = self._at_index(hourly.get("visibility"), now_index)
        uv_index = self._at_index(hourly.get("uv_index"), now_index)

        outlook = []
        for i, day in enumerate(daily.get("time") or []):
            outlook.append({
                "date": day,
                "tmax": self._at_index(daily.get("temperature_2m_max"), i),
                "tmin": self._at_index(daily.get("temperature_2m_min"), i),
                "code": self._at_index(daily.get("weather_code"), i),
            })

        return {
            "name": geo["name"],
            "sys": {"country": geo["country"]},
            "coords": {"lat": geo["lat"], "lon": geo["lon"]},
            "main": {
                "temp": current.get("temperature_2m", 0),
                "feels_like": current.get("apparent_temperature", 0),
                "humidity": current.get("relative_humidity_2m", 0),
                "pressure": current.get("pressure_msl", 0),
            },
            "weather": [{"main": main_condition, "description": description}],
            "wind": {"speed": current.get("wind_speed_10m", 0),
                     "deg": current.get("wind_direction_10m")},
            "clouds": {"all": current.get("cloud_cover", 0)},
            "visibility_m": visibility,
            "uv_index": uv_index,
            "outlook": outlook,
            "hourly": hourly,
            "astronomy": {
                "sunrise": (daily.get("sunrise") or [None])[0],
                "sunset": (daily.get("sunset") or [None])[0],
                "timezone": data.get("timezone", "local"),
            },
        }

    @staticmethod
    def _at_index(series, index):
        if not series or index is None or index >= len(series):
            return None
        return series[index]

    def _current_hour_index(self, times):
        """Index of the hourly slot covering now, or None."""
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        for index, stamp in enumerate(times):
            point = self._parse_weather_time(stamp)
            if point is not None and point >= now:
                return index
        return None

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

    def hourly_series(self, count=24):
        """Per-hour temperature and rain probability from here forward --
        the real series behind the forecast curve."""
        hourly = (self.weather_data or {}).get("hourly", {})
        times = hourly.get("time") or []
        temps = hourly.get("temperature_2m") or []
        rain = hourly.get("precipitation_probability") or []
        codes = hourly.get("weather_code") or []
        day_flags = hourly.get("is_day") or []
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        out = []
        for index, stamp in enumerate(times):
            point = self._parse_weather_time(stamp)
            if point is None or point < now or index >= len(temps):
                continue
            if temps[index] is None:
                continue
            out.append({
                "time": point,
                "temp": float(temps[index]),
                "rain": int(rain[index]) if index < len(rain) and rain[index] is not None else 0,
                "code": codes[index] if index < len(codes) else 0,
                "is_day": bool(day_flags[index]) if index < len(day_flags) else True,
            })
            if len(out) >= count:
                break
        return out

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
        """ENVIRONMENT: external atmospheric conditions.

        The full-screen sky animation paints straight to the display (it
        is deliberately wider than this module's zone); the instrument
        panel itself composites through the shared alpha layer.
        """
        if self.animation:
            self.animation.update()
            self.animation.draw(screen)
        self.check_time_based_moments()
        self.draw_instrument(screen, position, default=(300, 300))

    def _render_panel(self, surf, width, height, position=None):
        import theme
        accent = theme.module_accent('weather')
        pad = 6
        ix, iw = pad, width - pad * 2

        cur = self._panel_header(surf, ix, 0, iw, "Environment", accent,
                                 right_text="EXTERNAL")

        if not self.weather_data:
            msg = self._text('f_value', "SENSOR OFFLINE", COLOR_PASTEL_RED)
            surf.blit(msg, (ix, cur + 10))
            return

        main = self.weather_data.get('main', {})
        temp = main.get('temp', 0)
        feels = main.get('feels_like', temp)
        humidity = main.get('humidity', 0)
        pressure = main.get('pressure', 0)
        wind_block = self.weather_data.get('wind') or {}
        wind = wind_block.get('speed', 0) or 0
        wind_deg = wind_block.get('deg')
        cloud = (self.weather_data.get('clouds') or {}).get('all', 0)
        block = (self.weather_data.get('weather') or [{}])[0]
        condition = block.get('main', '')
        description = block.get('description', '')
        astro = self.astronomy()

        # Location block
        city = (self.weather_data.get('name') or '').upper()
        if city:
            name = self._text('f_micro', city, COLOR_FONT_BODY, spacing=3)
            surf.blit(name, (ix, cur))
            cur += name.get_height() + 1
        coords = self.weather_data.get('coords') or {}
        if coords.get('lat') is not None:
            lat, lon = float(coords['lat']), float(coords['lon'])
            text = (f"{abs(lat):.1f}N" if lat >= 0 else f"{abs(lat):.1f}S") + \
                   "   " + (f"{abs(lon):.1f}E" if lon >= 0 else f"{abs(lon):.1f}W")
            cs = self._text('f_nano', text, COLOR_TEXT_DIM, spacing=2)
            surf.blit(cs, (ix, cur))
            cur += cs.get_height() + 4

        remaining = height - cur - 4
        hero_h = int(min(112, remaining * 0.17))
        solar_h = int(min(76, remaining * 0.12))
        curve_h = int(min(168, remaining * 0.25))
        gauge_h = int(min(112, remaining * 0.17))
        outlook_h = int(min(92, remaining * 0.14))

        cur = self._draw_hero(surf, ix, cur, iw, hero_h, accent, temp, feels,
                              condition, description, astro)
        cur = self._draw_solar(surf, ix, cur + 4, iw, solar_h, accent, astro)
        cur = self._draw_forecast(surf, ix, cur + 6, iw, curve_h, accent)
        cur = self._draw_env_gauges(surf, ix, cur + 6, iw, gauge_h, accent,
                                    wind, wind_deg, humidity, cloud)
        cur = self._draw_readouts(surf, ix, cur + 4, iw, accent, pressure, height)
        cur = self._draw_outlook(surf, ix, cur + 6, iw, outlook_h, accent, height)

        if cur + 12 < height:
            src = (self.weather_source or 'no source').upper()
            tag = self._text('f_nano', src, COLOR_TEXT_DIM, spacing=1)
            surf.blit(tag, (ix + iw - tag.get_width(), cur + 2))

    def day_range(self):
        """Today's real high/low from the daily forecast, falling back to
        the next 24 hours of the hourly series."""
        outlook = (self.weather_data or {}).get('outlook') or []
        if outlook and outlook[0].get('tmax') is not None:
            return outlook[0]['tmax'], outlook[0]['tmin']
        series = self.hourly_series(24)
        if not series:
            return None, None
        temps = [p['temp'] for p in series]
        return max(temps), min(temps)

    def _draw_hero(self, surf, x, y, w, h, accent, temp, feels,
                   condition, description, astro):
        import weather_glyphs
        t = pygame.time.get_ticks() / 1000.0

        glyph_size = min(h * 1.0, w * 0.40)
        gx = x + glyph_size * 0.46
        gy = y + h * 0.44
        weather_glyphs.draw_condition(
            surf, gx, gy, glyph_size, accent, condition, description,
            is_day=astro['is_day'], t=t, phase=astro['moon_phase'])

        div_x = x + w * 0.42
        pygame.draw.line(surf, (*accent, 70), (div_x, y + 4), (div_x, y + h - 14), 1)

        color = self.get_temperature_color(temp)
        hero = self._text('f_hero', f"{temp:.0f}", color)
        hx = div_x + 12
        hy = y + 2
        draw_hero_glow(surf, hero, hx, hy, color, intensity=1.0 if IS_NIGHT else 0.35)
        surf.blit(hero, (hx, hy))
        pygame.draw.circle(surf, (*COLOR_TEXT_SECONDARY, 210),
                           (int(hx + hero.get_width() + 6), int(hy + 11)), 3, 1)
        deg = self._text('f_value', "C", COLOR_TEXT_SECONDARY)
        surf.blit(deg, (hx + hero.get_width() + 11, hy + 6))

        cur = hy + hero.get_height() + 1
        desc = self._text('f_micro', description.upper()[:20], COLOR_FONT_BODY, spacing=1)
        surf.blit(desc, (div_x + 12, cur))
        cur += desc.get_height() + 2
        fl = self._text('f_nano', f"FEELS LIKE {feels:.0f}C", COLOR_TEXT_DIM, spacing=1)
        surf.blit(fl, (div_x + 12, cur))

        # Real daily high/low from the forecast, with direction arrows
        tmax, tmin = self.day_range()
        if tmax is not None:
            rx = x + w
            ry = y + 4
            for arrow, value, label, col in (
                    ("^", tmax, "HIGH", COLOR_ACCENT_AMBER),
                    ("v", tmin, "LOW", COLOR_ACCENT_BLUE)):
                val = self._text('f_value', f"{value:.0f}", COLOR_FONT_BODY)
                lab = self._text('f_nano', label, COLOR_TEXT_DIM, spacing=1)
                surf.blit(val, (rx - val.get_width(), ry))
                tip_y = ry + val.get_height() / 2
                ax = rx - val.get_width() - 9
                if arrow == "^":
                    pts = [(ax, tip_y - 5), (ax - 4, tip_y + 2), (ax + 4, tip_y + 2)]
                else:
                    pts = [(ax, tip_y + 5), (ax - 4, tip_y - 2), (ax + 4, tip_y - 2)]
                pygame.draw.polygon(surf, (*col, 230), pts)
                surf.blit(lab, (rx - lab.get_width(), ry + val.get_height() - 1))
                ry += val.get_height() + lab.get_height() + 4
        return y + h

    def _draw_solar(self, surf, x, y, w, h, accent, astro):
        """Sun/moon travelling a real arc between the actual sunrise and
        sunset times, with a horizon line."""
        from effects_kit import draw_arc_segment
        cx = x + w / 2
        r = min(w * 0.40, h * 0.86)
        base = y + h - 14

        draw_arc_segment(surf, cx, base, r, 180, 360, accent, thickness=1, alpha=70)
        pygame.draw.line(surf, (*accent, 55), (x, base), (x + w, base), 1)
        for i in range(9):
            ang = math.radians(180 + i * 22.5)
            tx, ty = cx + math.cos(ang) * r, base + math.sin(ang) * r
            pygame.draw.line(surf, (*accent, 90), (tx, ty),
                             (tx + math.cos(ang) * 4, ty + math.sin(ang) * 4), 1)

        # The arc spans whichever period is actually running: sunrise to
        # sunset by day, sunset to the next sunrise by night. Showing the
        # moon travelling a sunrise-to-sunset arc reads as simply wrong.
        now = datetime.now()
        is_day = astro['is_day']
        if is_day:
            left_t, right_t = astro['sunrise'], astro['sunset']
            progress = astro['sun_progress']
        else:
            if now >= astro['sunset']:
                left_t = astro['sunset']
                right_t = astro['sunrise'] + timedelta(days=1)
            else:
                left_t = astro['sunset'] - timedelta(days=1)
                right_t = astro['sunrise']
            total = max(1.0, (right_t - left_t).total_seconds())
            progress = min(1.0, max(0.0, (now - left_t).total_seconds() / total))

        ang = math.radians(180 + 180 * max(0.0, min(1.0, progress)))
        mx, my = cx + math.cos(ang) * r, base + math.sin(ang) * r
        body_color = (255, 214, 140) if is_day else (190, 220, 255)
        glow = glow_sprite(11, body_color, 95, core_frac=0.3)
        surf.blit(glow, (mx - glow.get_width() / 2, my - glow.get_height() / 2))
        pygame.draw.circle(surf, (*body_color, 245), (int(mx), int(my)), 4)

        rise = self._text('f_nano', left_t.strftime("%H:%M"), COLOR_TEXT_DIM)
        setl = self._text('f_nano', right_t.strftime("%H:%M"), COLOR_TEXT_DIM)
        surf.blit(rise, (x, base + 3))
        surf.blit(setl, (x + w - setl.get_width(), base + 3))
        tag = self._text('f_nano', "DAYLIGHT" if is_day else "NIGHT", accent, spacing=2)
        surf.blit(tag, (cx - tag.get_width() / 2, base + 3))
        return y + h

    def _draw_forecast(self, surf, x, y, w, h, accent):
        """Real hourly temperature curve: condition glyphs and temperatures
        at three-hourly marks, rain probability beneath, calibrated axis."""
        import weather_glyphs
        from effects_kit import draw_chamfer_frame
        draw_chamfer_frame(surf, x, y, w, h, accent, alpha=50, cut=8)
        pad = 8
        lbl = self._text('f_nano', "24 HOUR FORECAST", accent, spacing=2)
        surf.blit(lbl, (x + pad, y + 5))
        today = self._text('f_nano', "TODAY", COLOR_TEXT_DIM, spacing=1)
        surf.blit(today, (x + w - pad - today.get_width(), y + 5))

        series = self.hourly_series(24)
        axis_w = 22
        plot_x = x + pad
        plot_w = w - pad * 2 - axis_w
        glyph_y = y + 20
        label_y = glyph_y + 19
        plot_y = label_y + 13
        plot_h = (y + h - 16) - plot_y
        if len(series) < 2 or plot_h < 20:
            none = self._text('f_nano', "NO FORECAST DATA", COLOR_TEXT_DIM, spacing=1)
            surf.blit(none, (x + w / 2 - none.get_width() / 2, y + h / 2))
            return y + h

        temps = [p['temp'] for p in series]
        lo, hi = min(temps), max(temps)
        span = max(1.0, hi - lo)
        lo_p, hi_p = lo - span * 0.25, hi + span * 0.25
        span_p = hi_p - lo_p
        col_w = plot_w / len(series)

        # Rain probability columns sit under the curve
        for i, point in enumerate(series):
            if point['rain'] <= 0:
                continue
            bar_h = plot_h * (point['rain'] / 100.0) * 0.5
            bx = plot_x + i * col_w
            pygame.draw.rect(surf, (90, 170, 235, 60),
                             (int(bx), int(plot_y + plot_h - bar_h),
                              max(1, int(col_w - 1)), int(bar_h)))

        pts = [(plot_x + i * col_w + col_w / 2,
                plot_y + plot_h - ((p['temp'] - lo_p) / span_p) * plot_h)
               for i, p in enumerate(series)]

        # Right-hand temperature axis
        for frac in (0.0, 0.5, 1.0):
            ty = plot_y + plot_h * (1.0 - frac)
            value = lo_p + span_p * frac
            pygame.draw.line(surf, (*accent, 35),
                             (plot_x, ty), (plot_x + plot_w, ty), 1)
            al = self._text('f_nano', f"{value:.0f}", COLOR_TEXT_DIM)
            surf.blit(al, (plot_x + plot_w + 5, ty - al.get_height() / 2))

        pygame.draw.lines(surf, (*accent, 230), False, pts, 2)

        # Marks every four hours: dropline, node, temperature, glyph
        step = max(1, len(series) // 5)
        t = pygame.time.get_ticks() / 1000.0
        for i in range(0, len(series), step):
            point = series[i]
            px, py = pts[i]
            for dy in range(int(py), int(plot_y + plot_h), 5):
                pygame.draw.line(surf, (*accent, 55), (px, dy), (px, dy + 2), 1)
            pygame.draw.circle(surf, (*accent, 245), (int(px), int(py)), 3)
            tl = self._text('f_nano', f"{point['temp']:.0f}", COLOR_FONT_BODY)
            surf.blit(tl, (px - tl.get_width() / 2, label_y))
            cond, desc = weather_glyphs.code_condition(point.get('code'))
            weather_glyphs.draw_condition(
                surf, px, glyph_y + 8, 23, accent, cond, desc,
                is_day=point.get('is_day', True), t=t)
            hl = self._text('f_nano', point['time'].strftime("%H"), COLOR_TEXT_DIM)
            surf.blit(hl, (px - hl.get_width() / 2, plot_y + plot_h + 3))

        pygame.draw.circle(surf, (255, 255, 255, 255),
                           (int(pts[0][0]), int(pts[0][1])), 3)
        return y + h

    def _draw_env_gauges(self, surf, x, y, w, h, accent, wind, wind_deg, humidity, cloud):
        import weather_glyphs
        from effects_kit import draw_segmented_ring
        r = int(min(h * 0.32, w * 0.145))
        cy = y + r + 12
        step = w / 3.0

        # Wind as a real compass rose on the reported bearing
        cx = x + step * 0.5
        weather_glyphs.wind_compass(surf, cx, cy - r * 0.16, r, accent, wind_deg)
        # South is left off: the speed readout lives in that lower segment,
        # and a letter there collides with it at this size.
        for label, ang in (("N", -90), ("E", 0), ("W", 180)):
            lx = cx + math.cos(math.radians(ang)) * (r - 12)
            ly = cy - r * 0.16 + math.sin(math.radians(ang)) * (r - 12)
            ls = self._text('f_nano', label, COLOR_TEXT_DIM)
            surf.blit(ls, (lx - ls.get_width() / 2, ly - ls.get_height() / 2))
        spd = self._text('f_small', f"{wind:.0f}", COLOR_FONT_BODY)
        un = self._text('f_nano', "M/S", COLOR_TEXT_DIM)
        total = spd.get_width() + un.get_width() + 3
        sy = cy + r * 0.34
        surf.blit(spd, (cx - total / 2, sy))
        surf.blit(un, (cx - total / 2 + spd.get_width() + 3, sy + 5))
        wl = self._text('f_nano', "WIND " + weather_glyphs.compass_label(wind_deg),
                        accent, spacing=1)
        surf.blit(wl, (cx - wl.get_width() / 2, cy + r + 6))

        rings = [
            ("HUMIDITY", humidity, self._humidity_word(humidity), weather_glyphs.icon_droplet),
            ("CLOUD", cloud, self._cloud_word(cloud), None),
        ]
        for i, (label, value, word, icon) in enumerate(rings):
            gx = x + step * (1.5 + i)
            frac = max(0.0, min(1.0, float(value) / 100.0))
            draw_segmented_ring(surf, gx, cy, r, frac, accent, segments=24, thickness=6)
            if icon:
                icon(surf, gx, cy - r * 0.56, 5, accent)
            val = self._text('f_small', f"{value:.0f}", COLOR_FONT_BODY)
            pct = self._text('f_nano', "%", COLOR_TEXT_DIM)
            total = val.get_width() + pct.get_width()
            surf.blit(val, (gx - total / 2, cy - val.get_height() / 2 + 1))
            surf.blit(pct, (gx - total / 2 + val.get_width(), cy + 1))
            wd = self._text('f_nano', word, COLOR_TEXT_DIM)
            surf.blit(wd, (gx - wd.get_width() / 2, cy + r * 0.56))
            lb = self._text('f_nano', label, accent, spacing=1)
            surf.blit(lb, (gx - lb.get_width() / 2, cy + r + 6))
        return cy + r + 18

    @staticmethod
    def _humidity_word(value):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return ""
        if v < 30:
            return "DRY"
        if v < 60:
            return "COMFORTABLE"
        if v < 80:
            return "HUMID"
        return "SATURATED"

    @staticmethod
    def _cloud_word(value):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return ""
        if v < 15:
            return "CLEAR"
        if v < 50:
            return "SCATTERED"
        if v < 85:
            return "BROKEN"
        return "OVERCAST"

    @staticmethod
    def _uv_word(value):
        if value is None:
            return "--", COLOR_TEXT_DIM
        v = float(value)
        if v < 3:
            return "LOW", COLOR_ACCENT_GREEN
        if v < 6:
            return "MODERATE", COLOR_ACCENT_AMBER
        if v < 8:
            return "HIGH", COLOR_ACCENT_AMBER
        return "VERY HIGH", COLOR_ACCENT_RED

    def _draw_readouts(self, surf, x, y, w, accent, pressure, height):
        """The instrument readings that do not warrant their own gauge."""
        import weather_glyphs
        visibility = self.weather_data.get('visibility_m')
        uv = self.weather_data.get('uv_index')
        uv_word, uv_color = self._uv_word(uv)

        rows = [
            (weather_glyphs.icon_gauge, "PRESSURE",
             f"{float(pressure):.0f} HPA" if pressure else "--", COLOR_FONT_BODY),
            (weather_glyphs.icon_eye, "VISIBILITY",
             f"{float(visibility) / 1000.0:.0f} KM" if visibility else "--", COLOR_FONT_BODY),
            (weather_glyphs.icon_uv, "UV INDEX",
             f"{float(uv):.0f}  {uv_word}" if uv is not None else "--", uv_color),
        ]
        cur = y
        for icon, label, value, color in rows:
            if cur + 16 > height:
                break
            icon(surf, x + 6, cur + 6, 5, accent)
            lb = self._text('f_nano', label, COLOR_TEXT_SECONDARY, spacing=1)
            surf.blit(lb, (x + 17, cur + 1))
            vl = self._text('f_nano', value, color, spacing=1)
            surf.blit(vl, (x + w - vl.get_width(), cur + 1))
            pygame.draw.line(surf, (*accent, 28), (x, cur + 15), (x + w, cur + 15), 1)
            cur += 17
        return cur

    def _draw_outlook(self, surf, x, y, w, h, accent, height):
        """Multi-day outlook cards from the real daily forecast."""
        import weather_glyphs
        outlook = (self.weather_data or {}).get('outlook') or []
        if len(outlook) < 2 or y + 40 > height:
            return y
        lbl = self._text('f_nano', "4 DAY OUTLOOK", accent, spacing=2)
        surf.blit(lbl, (x, y))
        cur = y + lbl.get_height() + 4

        days = outlook[:4]
        step = w / len(days)
        t = pygame.time.get_ticks() / 1000.0
        card_h = min(h - (cur - y), height - cur - 2)
        for i, day in enumerate(days):
            cx = x + step * (i + 0.5)
            try:
                label = datetime.strptime(day['date'], "%Y-%m-%d").strftime("%a").upper()
            except (ValueError, TypeError):
                label = "--"
            if i == 0:
                # Today gets viewfinder brackets rather than a filled box
                bx, by = x + step * i + 3, cur - 2
                bw, bh = step - 6, card_h
                for (ax, ay), (dx, dy) in (
                        ((bx, by), (1, 1)), ((bx + bw, by), (-1, 1)),
                        ((bx, by + bh), (1, -1)), ((bx + bw, by + bh), (-1, -1))):
                    pygame.draw.line(surf, (*accent, 200), (ax, ay), (ax + 7 * dx, ay), 1)
                    pygame.draw.line(surf, (*accent, 200), (ax, ay), (ax, ay + 7 * dy), 1)
            dl = self._text('f_nano', label, accent if i == 0 else COLOR_TEXT_DIM, spacing=1)
            surf.blit(dl, (cx - dl.get_width() / 2, cur))
            cond, desc = weather_glyphs.code_condition(day.get('code'))
            weather_glyphs.draw_condition(surf, cx, cur + 24, 24, accent,
                                          cond, desc, is_day=True, t=t)
            tmax = day.get('tmax')
            tmin = day.get('tmin')
            if tmax is not None:
                hi = self._text('f_nano', f"{tmax:.0f}", COLOR_FONT_BODY)
                sep = self._text('f_nano', "/", COLOR_TEXT_DIM)
                lo = self._text('f_nano', f"{tmin:.0f}", COLOR_TEXT_DIM)
                total = hi.get_width() + sep.get_width() + lo.get_width() + 4
                tx = cx - total / 2
                ty = cur + 38
                surf.blit(hi, (tx, ty))
                surf.blit(sep, (tx + hi.get_width() + 2, ty))
                surf.blit(lo, (tx + hi.get_width() + sep.get_width() + 4, ty))
        return cur + card_h

    def cleanup(self):
        pass
