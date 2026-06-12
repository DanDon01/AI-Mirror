"""Render a full-screen design preview of the mirror UI to a PNG.

Headless (no display, no network): every module is fed realistic fake
data and drawn once at portrait resolution, then saved to
data/preview.png. Use this on the dev box to judge layout/typography
changes without deploying to the Pi.

    python design_preview.py [condition]

condition: clear | partly | clouds | rain | storm | snow (default partly).
Also saves a banner close-up to data/preview_banner.png.
"""

import os
import sys
from datetime import datetime, timedelta

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()

WIDTH, HEIGHT = 1440, 2560
CONDITION = (sys.argv[1] if len(sys.argv) > 1 else "partly").lower()

CONDITION_DATA = {
    "clear": ("clear", "clear sky", 3.0),
    "partly": ("clouds", "partly cloudy", 3.4),
    "clouds": ("clouds", "overcast", 5.0),
    "rain": ("rain", "moderate rain", 9.5),
    "storm": ("thunderstorm", "thunderstorm", 11.0),
    "snow": ("snow", "moderate snowfall", 2.5),
}

from config import CONFIG
from layout_manager import LayoutManager
from clock_module import ClockModule
from weather_module import WeatherModule
from calendar_module import CalendarModule
from greeting_module import GreetingModule
from quote_module import QuoteModule
from news_module import NewsModule
from smarthome_module import SmartHomeModule
from countdown_module import CountdownModule
from fitbit_module import FitbitModule
from stocks_module import StocksModule
from sysinfo_module import SysInfoModule


def fake_weather(module):
    main, desc, wind = CONDITION_DATA.get(CONDITION, CONDITION_DATA["partly"])
    module.weather_data = {
        "name": "Birmingham",
        "sys": {"country": "GB"},
        "main": {"temp": 14.2, "feels_like": 12.1, "humidity": 64, "pressure": 1018},
        "weather": [{"main": main, "description": desc}],
        "wind": {"speed": wind},
        "clouds": {"all": 40},
    }
    module.weather_source = "Open-Meteo"
    module.update_animation()


def fake_calendar(module):
    now = datetime.now()
    module.events = [
        {"start": {"dateTime": (now + timedelta(hours=3)).isoformat()},
         "summary": "Team standup", "colorId": "1",
         "organizer": {"email": "work@example.com"}},
        {"start": {"dateTime": (now + timedelta(days=1, hours=2)).isoformat()},
         "summary": "Dentist appointment", "colorId": "4",
         "organizer": {"email": "home@example.com"}},
        {"start": {"date": (now + timedelta(days=3)).strftime("%Y-%m-%d")},
         "summary": "Mum's birthday", "colorId": "6",
         "organizer": {"email": "home@example.com"}},
    ]


def fake_news(module):
    module.headlines = [
        {"title": "Scientists confirm morning coffee improves mirror conversations",
         "source": "BBC", "link": "", "published": ""},
        {"title": "Local area news headline appears here", "source": "Guardian",
         "link": "", "published": ""},
    ]
    module.current_index = 0


def fake_smarthome(module):
    module._apply_states([
        {"entity_id": "light.hall", "state": "on",
         "attributes": {"friendly_name": "Hall Light"}},
        {"entity_id": "light.kitchen", "state": "off",
         "attributes": {"friendly_name": "Kitchen"}},
        {"entity_id": "climate.living", "state": "21.4",
         "attributes": {"friendly_name": "Living Room", "unit_of_measurement": "C"}},
        {"entity_id": "sensor.outside", "state": "12.1",
         "attributes": {"friendly_name": "Outside", "unit_of_measurement": "C"}},
        {"entity_id": "lock.front", "state": "locked",
         "attributes": {"friendly_name": "Front Door"}},
        {"entity_id": "switch.heater", "state": "on",
         "attributes": {"friendly_name": "Heater"}},
    ])


def fake_fitbit(module):
    module.data = {
        "steps": "7842", "calories": "1936", "active_minutes": 42,
        "sleep": "07:12", "resting_heart_rate": "58",
    }


def fake_stocks(module):
    prices = {
        "AAPL": (231.40, 1.24), "GOOGL": (188.12, -0.42), "MSFT": (452.08, 0.66),
        "TSLA": (242.55, -2.10), "NVDA": (138.20, 3.05), "AMD": (162.33, 0.12),
        "RR.L": (612.40, 0.88), "LLOY.L": (61.22, -0.31),
    }
    for t, (price, pct) in prices.items():
        currency = "GBp" if t.endswith(".L") else "$"
        module.stock_data[t] = {
            "price": price, "percent_change": pct, "currency": currency,
        }


def main():
    screen = pygame.Surface((WIDTH, HEIGHT))
    screen.fill((0, 0, 0))
    layout = LayoutManager(WIDTH, HEIGHT)

    clock = ClockModule(**CONFIG["clock"]["params"])
    clock.set_status_indicators("14C  partly cloudy")

    weather = WeatherModule(
        api_key="", city="Birmingham,UK", screen_width=WIDTH, screen_height=HEIGHT
    )
    fake_weather(weather)

    cal = CalendarModule(dict(CONFIG["calendar"]["params"]["config"]))
    fake_calendar(cal)

    greeting = GreetingModule(rotation_interval=60)
    greeting.update()

    quote = QuoteModule()
    quote.current_quote = "Simplicity is the ultimate sophistication."
    quote.current_author = "Leonardo da Vinci"

    news = NewsModule()
    fake_news(news)

    smarthome = SmartHomeModule("http://preview", "token")
    fake_smarthome(smarthome)

    countdown = CountdownModule(**CONFIG["countdown"]["params"])
    countdown.update()

    fitbit = FitbitModule(
        {"client_id": "x", "client_secret": "x", "access_token": "x",
         "refresh_token": "x"},
        {"time": None},
    )
    fake_fitbit(fitbit)

    stocks = StocksModule(tickers=list(CONFIG["stocks"]["params"]["tickers"]))
    fake_stocks(stocks)

    sysinfo = SysInfoModule(update_interval_seconds=10)
    try:
        sysinfo.update()
    except Exception:
        pass

    modules = {
        "weather": weather, "calendar": cal, "countdown": countdown,
        "smarthome": smarthome, "greeting": greeting, "quote": quote,
        "news": news, "fitbit": fitbit, "sysinfo": sysinfo,
    }

    # Let the banner ambience settle (cloud spread, drop distribution)
    # before the single draw pass; weather.draw renders the animation
    if weather.animation:
        for _ in range(90):
            weather.animation.update()

    for name, module in modules.items():
        pos = layout.get_module_position(name)
        if not pos:
            continue
        try:
            module.draw(screen, pos)
        except Exception as e:
            print(f"draw failed for {name}: {e}")

    clock.draw(screen, layout.get_module_position("clock")
               or {"x": 0, "y": 0, "width": WIDTH, "height": 95})
    stocks.draw_scrolling_ticker(screen)

    os.makedirs("data", exist_ok=True)
    out = os.path.join("data", "preview.png")
    pygame.image.save(screen, out)

    # Banner close-up for judging the weather ambience
    banner = screen.subsurface(pygame.Rect(0, 0, WIDTH, 150)).copy()
    banner_out = os.path.join("data", "preview_banner.png")
    pygame.image.save(banner, banner_out)
    print(f"saved {out} and {banner_out} (condition: {CONDITION})")


if __name__ == "__main__":
    main()
