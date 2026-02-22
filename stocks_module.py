"""Stock ticker module for AI-Mirror.

Loads watchlist from documentation/Portfolio_Watchlist_DDMMYYYY.csv.
Primary data source: Alpha Vantage GLOBAL_QUOTE (free tier, 25 calls/day).
Fallback: yfinance.

Fetch scheduling:
  - Non-blocking queue: processes 1 ticker per update() call (no main-loop freeze).
  - 3 daily windows: UK open+30m, US open+30m, US close-30m.
  - AV budget rotates across rounds so all tickers get AV data over time.
  - yfinance fills any tickers AV cannot cover.
"""

import os
import csv
import glob
import requests
import pygame
import logging
import time
import traceback
from datetime import datetime, timedelta
from pytz import timezone as pytz_tz
from config import (
    FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT,
    COLOR_PASTEL_GREEN, COLOR_PASTEL_RED, LINE_SPACING,
    TRANSPARENCY, CONFIG,
)
from visual_effects import VisualEffects
from api_tracker import api_tracker

logger = logging.getLogger("stocks")

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_CSV_DIR = os.path.join(_PROJECT_DIR, 'documentation')

# Alpha Vantage free tier: 25/day.  Keep 1 spare.
AV_DAILY_BUDGET = 24
AV_CALL_INTERVAL = 13   # seconds between AV requests (~5/min)
YF_CALL_INTERVAL = 2    # seconds between yfinance requests

# Exchange suffixes to strip (not London)
_STRIP_SUFFIXES = ('.O', '.K', '.PK')


def _normalize_csv_symbol(raw_symbol, exchange):
    """Convert a CSV symbol + exchange to (ticker, metadata dict)."""
    raw_symbol = raw_symbol.strip().strip('"')
    exchange = exchange.strip().strip('"')

    # Crypto pair (e.g. BTC/USD)
    if '/' in raw_symbol:
        return raw_symbol, {
            'market': 'crypto',
            'av_symbol': None,
            'yf_symbol': raw_symbol.replace('/', '-'),
            'currency': '$',
        }

    # London Stock Exchange
    if exchange == 'LON' or raw_symbol.endswith('.L'):
        ticker = raw_symbol if raw_symbol.endswith('.L') else raw_symbol + '.L'
        return ticker, {
            'market': 'UK',
            'av_symbol': ticker[:-2] + '.LON',
            'yf_symbol': ticker,
            'currency': '\u00a3',
        }

    # US / OTC -- strip exchange suffix (.O, .K, .PK)
    base = raw_symbol
    for suffix in _STRIP_SUFFIXES:
        if raw_symbol.endswith(suffix):
            base = raw_symbol[:-len(suffix)]
            break

    return base, {
        'market': 'OTC' if exchange == 'OTC' else 'US',
        'av_symbol': base,
        'yf_symbol': base,
        'currency': '$',
    }


class StocksModule:
    def __init__(self, tickers, alpha_vantage_key='', market_timezone='America/New_York'):
        self.default_tickers = list(tickers)
        self.alpha_vantage_key = alpha_vantage_key
        self.stock_data = {}
        self._ticker_meta = {}

        # CSV tracking
        self._csv_date_str = None
        self._last_csv_check = 0

        # Load tickers from CSV, fall back to config list
        self.tickers = []
        self._load_tickers_from_csv()
        if not self.tickers:
            self.tickers = list(tickers)
            for t in self.tickers:
                self._ticker_meta[t] = {
                    'market': 'UK' if t.endswith('.L') else 'US',
                    'av_symbol': t[:-2] + '.LON' if t.endswith('.L') else t,
                    'yf_symbol': t,
                    'currency': '\u00a3' if t.endswith('.L') else '$',
                }

        # Non-blocking fetch queue
        self._fetch_queue = []          # [(ticker, 'av'|'yf'), ...]
        self._last_fetch_call = 0
        self._queue_complete_pending = False

        # Daily budget / round tracking
        self._fetch_day = None
        self._av_calls_today = 0
        self._rotation_offset = 0      # rotate AV priority each round
        self._rounds_today = 0
        self._last_round_hour = -1
        self._initial_fetch_done = False

        # Timezone helpers for fetch windows
        self._uk_tz = pytz_tz('Europe/London')
        self._us_tz = pytz_tz('America/New_York')

        # Fonts
        try:
            self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE)
        except Exception:
            self.font = pygame.font.Font(None, FONT_SIZE)
        self.ticker_font = pygame.font.SysFont(FONT_NAME, 24)
        self.alert_font = pygame.font.SysFont(FONT_NAME, 32)
        self.markets_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE + 4)
        self.status_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE - 6)

        # Scroll state
        self.scroll_position = 0
        self.scroll_speed = 0.8
        self.alerts = []

        # Visual effects
        self.effects = VisualEffects()
        self.animation_start_time = time.time()
        self.item_fade_offsets = {t: i * 0.2 for i, t in enumerate(self.tickers)}
        self.header_pulse_speed = 0.3
        self.alert_pulse_speed = 0.8
        self.alert_bg_color = (60, 20, 20)
        self._notify = None
        self._prev_changes = {}

        logger.info(
            f"StocksModule: {len(self.tickers)} tickers, "
            f"AV key={'yes' if alpha_vantage_key else 'no'}"
        )

    def set_notification_callback(self, callback):
        self._notify = callback

    # ------------------------------------------------------------------
    # CSV loading
    # ------------------------------------------------------------------

    def _load_tickers_from_csv(self):
        """Find Portfolio_Watchlist_*.csv in documentation/, parse tickers."""
        try:
            pattern = os.path.join(_CSV_DIR, 'Portfolio_Watchlist_*.csv')
            files = glob.glob(pattern)
        except Exception:
            files = []

        if not files:
            logger.info("No watchlist CSV found in documentation/")
            return

        latest = sorted(files)[-1]
        filename = os.path.basename(latest)

        # Extract date portion: Portfolio_Watchlist_DDMMYYYY.csv
        date_part = filename.replace('Portfolio_Watchlist_', '').replace('.csv', '')

        if self._csv_date_str == date_part:
            return  # unchanged

        tickers = []
        meta = {}
        try:
            with open(latest, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw_sym = row.get('Symbol', '')
                    exchange = row.get('Exchange', '')
                    if not raw_sym.strip():
                        continue
                    ticker, info = _normalize_csv_symbol(raw_sym, exchange)
                    if ticker and ticker not in meta:
                        tickers.append(ticker)
                        meta[ticker] = info
        except Exception as e:
            logger.error(f"Error reading watchlist CSV {filename}: {e}")
            return

        self.tickers = tickers
        self._ticker_meta = meta
        self._csv_date_str = date_part
        self._initial_fetch_done = False
        self.item_fade_offsets = {t: i * 0.2 for i, t in enumerate(tickers)}
        logger.info(f"Loaded {len(tickers)} tickers from {filename}")

    def _check_csv_update(self):
        """Re-scan CSV directory for filename date changes."""
        old_date = self._csv_date_str
        self._load_tickers_from_csv()
        if self._csv_date_str != old_date and old_date is not None:
            logger.info(f"Watchlist CSV updated: {old_date} -> {self._csv_date_str}")
            current_set = set(self.tickers)
            for t in list(self.stock_data.keys()):
                if t not in current_set:
                    del self.stock_data[t]

    # ------------------------------------------------------------------
    # Fetch scheduling
    # ------------------------------------------------------------------

    def _populate_fetch_queue(self):
        """Build the non-blocking fetch queue for a new round.

        Assigns AV or yfinance source per ticker based on remaining daily
        budget.  Rotates which tickers get AV priority so every ticker
        gets high-quality data over successive rounds.
        """
        av_remaining = AV_DAILY_BUDGET - self._av_calls_today
        n = len(self.tickers)
        if n == 0:
            return

        offset = self._rotation_offset % n
        rotated = self.tickers[offset:] + self.tickers[:offset]

        queue = []
        av_count = 0
        for ticker in rotated:
            meta = self._ticker_meta.get(ticker, {})
            can_av = (
                meta.get('av_symbol')
                and meta.get('market') != 'crypto'
                and av_count < av_remaining
            )
            if can_av:
                queue.append((ticker, 'av'))
                av_count += 1
            else:
                queue.append((ticker, 'yf'))

        self._fetch_queue = queue
        self._rotation_offset += av_count
        self._rounds_today += 1
        logger.info(
            f"Fetch round {self._rounds_today}: "
            f"{av_count} AV + {len(queue) - av_count} yfinance "
            f"({av_remaining - av_count} AV budget left)"
        )

    def _is_fetch_window(self):
        """Return a window identifier if current time is inside a fetch window.

        Windows (30-minute duration each):
          8  -> UK open  + 30 min  (08:30-09:00 London)
          10 -> US open  + 30 min  (10:00-10:30 New York)
          15 -> US close - 30 min  (15:30-16:00 New York)

        Returns int window id or None.
        """
        now_utc = datetime.now(pytz_tz('UTC'))

        uk_now = now_utc.astimezone(self._uk_tz)
        if uk_now.hour == 8 and uk_now.minute >= 30:
            return 8

        us_now = now_utc.astimezone(self._us_tz)
        if us_now.hour == 10 and us_now.minute < 30:
            return 10
        if us_now.hour == 15 and us_now.minute >= 30:
            return 15

        return None

    # ------------------------------------------------------------------
    # Single-ticker fetch (non-blocking)
    # ------------------------------------------------------------------

    def _process_queue_item(self):
        """Pop one item from the queue and fetch it."""
        if not self._fetch_queue:
            return

        ticker, source = self._fetch_queue.pop(0)
        if source == 'av':
            self._fetch_single_av(ticker)
        else:
            self._fetch_single_yf(ticker)
        self._last_fetch_call = time.time()

        if not self._fetch_queue:
            self._queue_complete_pending = True

    def _fetch_single_av(self, ticker):
        """Fetch one ticker from Alpha Vantage GLOBAL_QUOTE."""
        meta = self._ticker_meta.get(ticker, {})
        av_symbol = meta.get('av_symbol', ticker)

        if not self.alpha_vantage_key:
            return
        if not api_tracker.allow("stocks", "alpha-vantage"):
            logger.debug(f"AV tracker limit, skipping {ticker}")
            return

        url = (
            f"https://www.alphavantage.co/query"
            f"?function=GLOBAL_QUOTE"
            f"&symbol={av_symbol}"
            f"&apikey={self.alpha_vantage_key}"
        )
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            api_tracker.record("stocks", "alpha-vantage")
            self._av_calls_today += 1
            data = resp.json()

            # Rate-limit / info message from AV
            if 'Note' in data or 'Information' in data:
                msg = data.get('Note', data.get('Information', ''))
                logger.warning(f"Alpha Vantage limit: {msg}")
                # Downgrade remaining AV items to yfinance
                self._fetch_queue = [
                    (t, 'yf') for t, _s in self._fetch_queue
                ]
                return

            quote = data.get('Global Quote', {})
            if not quote or '05. price' not in quote:
                logger.warning(f"No AV quote for {ticker} ({av_symbol})")
                return

            price = float(quote['05. price'])
            change_pct = float(quote.get('10. change percent', '0%').rstrip('%'))

            self.stock_data[ticker] = {
                'price': price,
                'percent_change': change_pct,
                'volume': int(quote.get('06. volume', 0)),
                'day_range': (
                    f"{quote.get('04. low', 'N/A')} - "
                    f"{quote.get('03. high', 'N/A')}"
                ),
                'source': 'alpha-vantage',
                'currency': meta.get('currency', '$'),
            }
            logger.info(f"AV: {ticker} = {price:.2f} ({change_pct:+.2f}%)")

        except requests.RequestException as e:
            logger.warning(f"AV request failed for {ticker}: {e}")
        except (ValueError, KeyError) as e:
            logger.warning(f"AV parse error for {ticker}: {e}")
        except Exception as e:
            logger.error(f"AV error for {ticker}: {e}")

    def _fetch_single_yf(self, ticker):
        """Fetch one ticker from yfinance (fallback)."""
        try:
            import yfinance as yf
        except ImportError:
            return

        meta = self._ticker_meta.get(ticker, {})
        yf_symbol = meta.get('yf_symbol', ticker)

        try:
            stock = yf.Ticker(yf_symbol)
            info = stock.fast_info
            if hasattr(info, 'regular_market_price') and info.regular_market_price:
                price = info.regular_market_price
                prev = getattr(info, 'previous_close', price) or price
                pct = ((price - prev) / prev) * 100 if prev else 0.0
                self.stock_data[ticker] = {
                    'price': price,
                    'percent_change': pct,
                    'volume': getattr(info, 'regular_market_volume', 0),
                    'day_range': (
                        f"{getattr(info, 'day_low', price):.2f} - "
                        f"{getattr(info, 'day_high', price):.2f}"
                    ),
                    'source': 'yfinance',
                    'currency': meta.get('currency', '$'),
                }
                logger.info(f"yfinance: {ticker} = {price:.2f} ({pct:+.2f}%)")
                api_tracker.record("stocks", "yahoo-finance")
        except Exception as e:
            logger.debug(f"yfinance failed for {ticker} ({yf_symbol}): {e}")

    # ------------------------------------------------------------------
    # Main update (non-blocking)
    # ------------------------------------------------------------------

    def update(self):
        """Non-blocking update.  Processes at most 1 ticker per call."""
        now = time.time()

        # Hourly CSV check
        if now - self._last_csv_check > 3600:
            self._check_csv_update()
            self._last_csv_check = now

        # Daily reset at midnight UTC
        today = datetime.now(pytz_tz('UTC')).date()
        if self._fetch_day != today:
            self._fetch_day = today
            self._av_calls_today = 0
            self._rounds_today = 0
            self._last_round_hour = -1
            self._initial_fetch_done = False
            logger.info("Daily stock tracker reset")

        # Process queue: respect per-source rate intervals
        if self._fetch_queue:
            next_source = self._fetch_queue[0][1]
            delay = AV_CALL_INTERVAL if next_source == 'av' else YF_CALL_INTERVAL
            if now - self._last_fetch_call >= delay:
                self._process_queue_item()
            return  # don't start new rounds while queue is active

        # Post-round notifications
        if self._queue_complete_pending:
            self._queue_complete_pending = False
            self._post_round_notifications()

        # Initial fetch (startup or after CSV reload)
        if not self._initial_fetch_done:
            self._initial_fetch_done = True
            self._populate_fetch_queue()
            return

        # Weekends: no further rounds after initial
        if today.weekday() >= 5:
            return

        # Check fetch windows
        window = self._is_fetch_window()
        if window is not None and window != self._last_round_hour:
            self._last_round_hour = window
            self._populate_fetch_queue()

    def _post_round_notifications(self):
        """Log round summary and push center notifications for big movers."""
        valid = sum(
            1 for d in self.stock_data.values()
            if isinstance(d.get('price'), (int, float))
        )
        logger.info(
            f"Fetch round complete: {valid}/{len(self.tickers)} with data"
        )

        if self._notify:
            for ticker, data in self.stock_data.items():
                pct = data.get('percent_change', 0)
                if isinstance(pct, (int, float)) and abs(pct) >= 5:
                    prev = self._prev_changes.get(ticker)
                    if prev is None or abs(prev) < 5:
                        arrow = "UP" if pct > 0 else "DOWN"
                        color = (
                            COLOR_PASTEL_GREEN if pct > 0 else COLOR_PASTEL_RED
                        )
                        self._notify(
                            f"{ticker} {arrow} {abs(pct):.1f}%",
                            color=color, duration_ms=6000,
                        )
            self._prev_changes = {
                t: d.get('percent_change', 0)
                for t, d in self.stock_data.items()
            }

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, screen, position):
        """Fallback grid view (primary path is draw_scrolling_ticker)."""
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 200)
            else:
                x, y = position
                width, height = 300, 200

            if not hasattr(self, '_grid_fonts_ready') or not self._grid_fonts_ready:
                from module_base import ModuleDrawHelper
                tf, bf, sf = ModuleDrawHelper.get_fonts()
                self.title_font = tf
                self.body_font = bf
                self.small_font = sf
                self._grid_fonts_ready = True

            from module_base import ModuleDrawHelper
            current_y = ModuleDrawHelper.draw_module_title(
                screen, "Stocks", x, y, width
            )

            if not self.stock_data:
                no_data = self.body_font.render(
                    "Loading stocks...", True, (140, 140, 140)
                )
                no_data.set_alpha(TRANSPARENCY)
                screen.blit(no_data, (x, current_y))
                return

            col_width = width // 2
            items = list(self.stock_data.items())[:8]

            for i, (ticker, data) in enumerate(items):
                col = i % 2
                row = i // 2
                item_x = x + col * col_width
                item_y = current_y + row * 30

                if item_y > y + height - 30:
                    break

                price = data.get('price', 'N/A')
                pct = data.get('percent_change', 0)

                if isinstance(pct, (int, float)):
                    color = self.determine_color(pct)
                    change_str = f"{'+' if pct >= 0 else ''}{pct:.2f}%"
                else:
                    color = (160, 160, 160)
                    change_str = "0.00%"

                currency = data.get('currency', '$')

                t_surf = self.body_font.render(ticker, True, (200, 200, 200))
                t_surf.set_alpha(TRANSPARENCY)
                screen.blit(t_surf, (item_x, item_y))

                if isinstance(price, (int, float)):
                    p_surf = self.small_font.render(
                        f"{currency}{price:.2f} {change_str}", True, color
                    )
                    p_surf.set_alpha(TRANSPARENCY)
                    screen.blit(p_surf, (item_x, item_y + 16))

        except Exception as e:
            logger.error(f"Error drawing stocks: {e}")
            logger.error(traceback.format_exc())

    def draw_scrolling_ticker(self, screen):
        """Seamless scrolling ticker at the bottom of the screen."""
        try:
            ticker_height = 40
            screen_width = screen.get_width()
            y = screen.get_height() - ticker_height

            if not self.stock_data:
                msg = "Loading stock data..."
                surf = self.ticker_font.render(msg, True, (140, 140, 140))
                surf.set_alpha(TRANSPARENCY)
                screen.blit(surf, ((screen_width - surf.get_width()) // 2, y + 8))
                return

            # Build per-ticker surfaces
            ticker_items = []
            total_width = 0
            for ticker in self.tickers:
                data = self.stock_data.get(ticker)
                if not data:
                    continue
                price = data.get('price', 'N/A')
                pct = data.get('percent_change', 0)
                if not isinstance(price, (int, float)):
                    continue

                if isinstance(pct, (int, float)):
                    change_str = (
                        f"{'+' if pct >= 0 else ''}{pct:.2f}%"
                    )
                    arrow = (
                        " \u25b2" if pct > 0
                        else " \u25bc" if pct < 0
                        else ""
                    )
                    color = self.determine_color(pct)
                else:
                    change_str = "0.00%"
                    arrow = ""
                    color = (160, 160, 160)

                currency = data.get('currency', '$')
                text = f"  {ticker}  {currency}{price:.2f}{arrow} {change_str}  "

                surf = self.ticker_font.render(text, True, color)
                surf.set_alpha(TRANSPARENCY)
                ticker_items.append(surf)
                total_width += surf.get_width()

            if not ticker_items:
                return

            # Seamless loop
            draw_x = self.scroll_position % total_width
            if draw_x > 0:
                draw_x -= total_width

            while draw_x < screen_width:
                for surf in ticker_items:
                    if draw_x + surf.get_width() > 0 and draw_x < screen_width:
                        screen.blit(surf, (draw_x, y + 8))
                    draw_x += surf.get_width()

            self.scroll_position -= self.scroll_speed
            if self.scroll_position < -total_width * 2:
                self.scroll_position += total_width

        except Exception as e:
            logger.error(f"Error drawing scrolling ticker: {e}")

    def draw_alerts(self, screen, position):
        x, y = position
        self.alerts = []
        for ticker, data in self.stock_data.items():
            pct = data.get('percent_change', 0)
            if isinstance(pct, (int, float)) and abs(pct) >= 5:
                self.alerts.append((ticker, pct))

        if self.alerts:
            alert_width = 280
            alert_height = len(self.alerts) * LINE_SPACING + 10
            alert_rect = pygame.Rect(x - 5, y - 5, alert_width, alert_height)
            alert_alpha = self.effects.pulse_effect(
                160, 220, self.alert_pulse_speed
            )
            self.effects.draw_rounded_rect(
                screen, alert_rect, self.alert_bg_color,
                radius=10, alpha=alert_alpha,
            )
            afont = pygame.font.SysFont(FONT_NAME, FONT_SIZE, bold=True)
            for ticker, pct in self.alerts:
                color = COLOR_PASTEL_GREEN if pct > 0 else COLOR_PASTEL_RED
                arrow_c = "^" if pct > 0 else "v"
                text = f"{ticker} {arrow_c} {abs(pct):.2f}%"
                tsurf = self.effects.create_text_with_shadow(
                    afont, text, color, offset=2
                )
                screen.blit(tsurf, (x, y))
                y += LINE_SPACING
            y += 5
        return y

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def determine_color(self, percent_change):
        default_color = (180, 180, 180)
        if not isinstance(percent_change, (int, float)):
            return default_color
        if percent_change > 0:
            return COLOR_PASTEL_GREEN
        elif percent_change < 0:
            return COLOR_PASTEL_RED
        return default_color

    def is_market_open(self, current_market_time, market):
        hours = {
            'US': (9, 30, 16, 0),
            'UK': (8, 0, 16, 30),
        }
        o_h, o_m, c_h, c_m = hours.get(market, (9, 30, 16, 0))
        t = current_market_time.time()
        from datetime import time as dt_time
        return dt_time(o_h, o_m) <= t < dt_time(c_h, c_m)

    def cleanup(self):
        pass
