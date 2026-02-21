import yfinance as yf
import pygame
import logging
from datetime import datetime, timedelta
from pytz import timezone
from config import FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_PASTEL_GREEN, COLOR_PASTEL_RED, LINE_SPACING, TRANSPARENCY, CONFIG
from visual_effects import VisualEffects
import time
import math
import traceback

# Color constants
COLOR_HEADER = (240, 240, 240)  # White for headers

class StocksModule:
    def __init__(self, tickers, market_timezone='America/New_York'):
        self.tickers = tickers
        self.stock_data = {}
        try:
            self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE)
        except Exception:
            logging.warning(f"Font '{FONT_NAME}' not found. Using default font.")
            self.font = pygame.font.Font(None, FONT_SIZE)
        self.market_timezones = {
            'US': timezone('America/New_York'),
            'UK': timezone('Europe/London')
        }
        self.update_interval = timedelta(minutes=10)  # Change this to your desired interval
        
        # Set last_update to a timezone-aware datetime
        self.last_update = datetime.now(timezone('UTC')) - self.update_interval
        self.market_hours = {
            'US': {
                'open': self.market_timezones['US'].localize(datetime.now().replace(hour=9, minute=30, second=0, microsecond=0)),
                'close': self.market_timezones['US'].localize(datetime.now().replace(hour=16, minute=0, second=0, microsecond=0))
            },
            'UK': {
                'open': self.market_timezones['UK'].localize(datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)),
                'close': self.market_timezones['UK'].localize(datetime.now().replace(hour=16, minute=30, second=0, microsecond=0))
            }
        }

        self.ticker_font = pygame.font.SysFont(FONT_NAME, 24)
        self.alert_font = pygame.font.SysFont(FONT_NAME, 32)
        self.scroll_position = 0
        self.scroll_speed = 0.8  # Reduced from 2 to 0.8 for slower scrolling
        self.alerts = []

        self.markets_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE + 4)
        self.status_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE - 6)

        # Add new visual properties
        self.effects = VisualEffects()
        self.animation_start_time = time.time()
        self.item_fade_offsets = {ticker: i * 0.2 for i, ticker in enumerate(tickers)}
        self.header_pulse_speed = 0.3
        self.alert_pulse_speed = 0.8
        
        self.alert_bg_color = (60, 20, 20)
        self._notify = None
        self._prev_changes = {}  # Track previous changes for notification dedup

    def set_notification_callback(self, callback):
        """Register a callback for center-screen notifications."""
        self._notify = callback

    def update(self):
        """Update stock data with minimal API calls to avoid rate limiting"""
        current_time = datetime.now(timezone('UTC'))
        
        # Check if it's time to update (use longer intervals to reduce API calls)
        if current_time - self.last_update < timedelta(minutes=30):  # Extend to 30 minutes
            return
        
        # Skip updates during weekends when markets are closed
        if current_time.weekday() >= 5:  # 5=Saturday, 6=Sunday
            self.logger.info("Skipping stock updates during weekend")
            return
        
        try:
            if not hasattr(self, 'logger'):
                self.logger = logging.getLogger('stocks_module')
            
            # Check if we've been rate-limited recently (wait longer)
            if hasattr(self, 'rate_limited') and self.rate_limited:
                time_since_rate_limit = time.time() - self.rate_limited_time
                if time_since_rate_limit < 3600 * 6:  # Wait 6 hours after being rate limited
                    self.logger.warning(f"Skipping Yahoo Finance due to rate limits (retry in {(3600*6-time_since_rate_limit)/60:.0f}m)")
                    return
            
            # Only test connection once, not for each ticker
            try:
                import socket
                socket.create_connection(("yahoo.com", 443), timeout=5)
                self.logger.info("Network connectivity confirmed")
            except Exception as e:
                self.logger.warning(f"Network issue: {e}")
                return
            
            # Update all tickers with batch fetching
            self.update_tickers_batch()
            
            self.last_update = current_time
            self.logger.info("Stock data update complete")

            # Push center notification for big movers (>5%)
            if self._notify:
                for ticker, data in self.stock_data.items():
                    pct = data.get('percent_change', 0)
                    if isinstance(pct, (int, float)) and abs(pct) >= 5:
                        prev = self._prev_changes.get(ticker)
                        if prev is None or abs(prev) < 5:
                            arrow = "UP" if pct > 0 else "DOWN"
                            color = COLOR_PASTEL_GREEN if pct > 0 else COLOR_PASTEL_RED
                            self._notify(
                                f"{ticker} {arrow} {abs(pct):.1f}%",
                                color=color,
                                duration_ms=6000,
                            )
                self._prev_changes = {
                    t: d.get('percent_change', 0) for t, d in self.stock_data.items()
                }
            
        except Exception as e:
            self.logger.error(f"Error updating stock data: {e}")

    def update_tickers_batch(self):
        """Update all tickers with minimal API calls"""
        try:
            # Attempt to use a single API call with multiple tickers
            tickers_str = " ".join(self.tickers)
            batch = yf.Tickers(tickers_str)
            
            # Check if we're already being rate limited
            for ticker in self.tickers[:1]:  # Just check one ticker to minimize requests
                try:
                    single = batch.tickers[ticker]
                    info = single.fast_info
                    if info is None or (hasattr(info, 'regular_market_price') and info.regular_market_price is None):
                        raise Exception("No data available")
                except Exception as e:
                    if "429" in str(e) or "Too Many Requests" in str(e):
                        self.logger.warning("Yahoo Finance API rate limited")
                        self.rate_limited = True
                        self.rate_limited_time = time.time()
                        return
            
            # Process each ticker but limit the API calls
            for ticker in self.tickers:
                try:
                    # Use the ticker from the batch to minimize requests
                    stock = batch.tickers[ticker]
                    
                    # Try getting price from fast_info first (less likely to be rate limited)
                    try:
                        info = stock.fast_info
                        if hasattr(info, 'regular_market_price') and info.regular_market_price is not None:
                            price = info.regular_market_price
                            prev_close = info.previous_close if hasattr(info, 'previous_close') else price
                            percent_change = ((price - prev_close) / prev_close) * 100 if prev_close != 0 else 0.0
                            
                            self.stock_data[ticker] = {
                                'price': price,
                                'percent_change': percent_change,
                                'volume': getattr(info, 'regular_market_volume', 0),
                                'day_range': f"{getattr(info, 'day_low', price):.2f} - {getattr(info, 'day_high', price):.2f}"
                            }
                            continue  # Skip to next ticker if successful
                    except Exception as e:
                        self.logger.debug(f"Fast info failed for {ticker}: {e}")
                    
                    # If we get here, we couldn't get data for this ticker
                    self.logger.warning(f"Could not get data for {ticker}")
                    self.stock_data[ticker] = {'price': 'N/A', 'percent_change': 'N/A', 'volume': 'N/A', 'day_range': 'N/A'}
                    
                except Exception as e:
                    self.logger.error(f"Error fetching {ticker}: {str(e)}")
                    self.stock_data[ticker] = {'price': 'N/A', 'percent_change': 'N/A', 'volume': 'N/A', 'day_range': 'N/A'}
                
                # Add delay between processing each ticker
                time.sleep(1.0)  # Longer delay to avoid rate limits
            
        except Exception as e:
            self.logger.error(f"Batch update failed: {e}")

    def draw(self, screen, position):
        """Draw stock data -- floating text on black, no background.

        This is the fallback grid view. The primary rendering path is
        draw_scrolling_ticker() called from AI-Mirror's draw_modules().
        """
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 200)
            else:
                x, y = position
                width, height = 300, 200

            styling = CONFIG.get('module_styling', {})
            line_height = styling.get('spacing', {}).get('line_height', 28)

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
                no_data = self.body_font.render("No stock data", True, (160, 160, 160))
                no_data.set_alpha(TRANSPARENCY)
                screen.blit(no_data, (x, current_y))
                return

            col_width = width // 2
            stocks_to_display = list(self.stock_data.items())[:8]

            for i, (ticker, data) in enumerate(stocks_to_display):
                col = i % 2
                row = i // 2
                item_x = x + col * col_width
                item_y = current_y + row * 30

                if item_y > y + height - 30:
                    break

                price = data.get('price', 'N/A')
                percent_change = data.get('percent_change', 0)

                if isinstance(percent_change, (int, float)):
                    color = self.determine_color(percent_change)
                    change_str = f"{'+' if percent_change >= 0 else ''}{percent_change:.2f}%"
                else:
                    color = (160, 160, 160)
                    change_str = "0.00%"

                currency_symbol = '\u00a3' if ticker.endswith('.L') else '$'

                ticker_surf = self.body_font.render(ticker, True, (200, 200, 200))
                ticker_surf.set_alpha(TRANSPARENCY)
                screen.blit(ticker_surf, (item_x, item_y))

                if isinstance(price, (int, float)):
                    price_surf = self.small_font.render(
                        f"{currency_symbol}{price:.2f} {change_str}", True, color
                    )
                    price_surf.set_alpha(TRANSPARENCY)
                    screen.blit(price_surf, (item_x, item_y + 16))

        except Exception as e:
            logging.error(f"Error drawing stocks: {e}")
            logging.error(traceback.format_exc())

    def draw_scrolling_ticker(self, screen):
        """Draw a seamless scrolling ticker at the bottom of the screen.

        Renders a thin separator line above the ticker, then loops ticker
        items to fill the visible width with no gaps.
        """
        try:
            ticker_height = 30
            screen_width = screen.get_width()
            y = screen.get_height() - ticker_height

            # Thin separator above ticker
            pygame.draw.line(screen, (40, 40, 40), (0, y - 1), (screen_width, y - 1), 1)

            if not self.stock_data:
                message = "Loading stock data..."
                text_surface = self.ticker_font.render(message, True, (160, 160, 160))
                text_surface.set_alpha(TRANSPARENCY)
                x_pos = (screen_width - text_surface.get_width()) // 2
                screen.blit(text_surface, (x_pos, y + 4))
                return

            # Build rendered surfaces for each ticker
            ticker_items = []
            total_width = 0
            for ticker, data in self.stock_data.items():
                price = data.get('price', 'N/A')
                percent_change = data.get('percent_change', 0)
                if price == 'N/A' or not isinstance(price, (int, float)):
                    continue

                if isinstance(percent_change, (int, float)):
                    change_str = f"{'+' if percent_change >= 0 else ''}{percent_change:.2f}%"
                    arrow = " \u25b2" if percent_change > 0 else " \u25bc" if percent_change < 0 else ""
                    color = self.determine_color(percent_change)
                else:
                    change_str = "0.00%"
                    arrow = ""
                    color = (160, 160, 160)

                currency = '\u00a3' if ticker.endswith('.L') else '$'
                text = f"  {ticker}  {currency}{price:.2f}{arrow} {change_str}  "

                surf = self.ticker_font.render(text, True, color)
                surf.set_alpha(TRANSPARENCY)
                ticker_items.append(surf)
                total_width += surf.get_width()

            if not ticker_items:
                return

            # Seamless loop: draw enough copies to fill the screen
            draw_x = self.scroll_position % total_width
            if draw_x > 0:
                draw_x -= total_width

            while draw_x < screen_width:
                for surf in ticker_items:
                    if draw_x + surf.get_width() > 0 and draw_x < screen_width:
                        screen.blit(surf, (draw_x, y + 4))
                    draw_x += surf.get_width()

            # Advance scroll
            self.scroll_position -= self.scroll_speed
            if self.scroll_position < -total_width * 2:
                self.scroll_position += total_width

        except Exception as e:
            logging.error(f"Error drawing scrolling ticker: {e}")

    def draw_alerts(self, screen, position):
        x, y = position
        current_time = datetime.now(timezone('UTC'))
        
        self.alerts = []
        for ticker, data in self.stock_data.items():
            percent_change = data['percent_change']
            if isinstance(percent_change, float) and abs(percent_change) >= 5:
                self.alerts.append((ticker, percent_change))
        
        if self.alerts:
            # Draw alert background with pulsing effect
            alert_width = 280  # Adjust based on your layout
            alert_height = len(self.alerts) * LINE_SPACING + 10
            alert_rect = pygame.Rect(x-5, y-5, alert_width, alert_height)
            
            # Pulse the alert background for attention
            alert_alpha = self.effects.pulse_effect(160, 220, self.alert_pulse_speed)
            self.effects.draw_rounded_rect(screen, alert_rect, self.alert_bg_color, radius=10, alpha=alert_alpha)
            
            logging.info(f"Displaying {len(self.alerts)} stock alerts")
            alert_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE, bold=True)
            
            for ticker, percent_change in self.alerts:
                color = COLOR_PASTEL_GREEN if percent_change > 0 else COLOR_PASTEL_RED
                
                # Create alert text with arrow indicator
                arrow = "▲" if percent_change > 0 else "▼"
                text = f"{ticker} {arrow} {abs(percent_change):.2f}%"
                
                # Create text with glow effect for alerts
                text_surface = self.effects.create_text_with_shadow(
                    alert_font, text, color, offset=2)
                
                screen.blit(text_surface, (x, y))
                y += LINE_SPACING
            
            y += 5  # Add a bit of extra space after alerts
        
        return y

    def is_market_open(self, current_market_time, market):
        market_hours = self.market_hours[market]
        return market_hours['open'].time() <= current_market_time.time() < market_hours['close'].time()

    def cleanup(self):
        pass  # No cleanup needed for this module

    def determine_color(self, percent_change):
        """Determine the color based on the percent change"""
        # Default color for invalid cases
        default_color = (180, 180, 180)  # Light gray
        
        # Handle N/A or string values
        if not isinstance(percent_change, (int, float)):
            return default_color
        
        try:
            if percent_change > 0:
                return COLOR_PASTEL_GREEN
            elif percent_change < 0:
                return COLOR_PASTEL_RED
            else:
                return default_color
        except Exception:
            return default_color  # Safe fallback

    def update_data(self):
        """Update stock data with more robust error handling and fallback"""
        try:
            # Use a slower, more reliable approach
            for ticker in self.tickers:
                try:
                    # Force longer timeframe to improve chances of getting data
                    ticker_data = yf.Ticker(ticker)
                    
                    # Try multiple timeframes
                    for period in ["1d", "5d", "1mo"]:
                        try:
                            history = ticker_data.history(period=period)
                            if not history.empty:
                                # We have data, use it and exit loop
                                current_price = history['Close'].iloc[-1]
                                if 'Open' in history and len(history['Open']) > 0:
                                    open_price = history['Open'].iloc[0]
                                    percent_change = ((current_price - open_price) / open_price) * 100
                                else:
                                    # Just use 0% change if we can't calculate it
                                    percent_change = 0.0
                                    
                                volume = history['Volume'].iloc[-1] if 'Volume' in history else 0
                                day_high = history['High'].iloc[-1] if 'High' in history else current_price
                                day_low = history['Low'].iloc[-1] if 'Low' in history else current_price
                                
                                self.stock_data[ticker] = {
                                    'price': current_price,
                                    'percent_change': percent_change,
                                    'volume': volume,
                                    'day_range': f"{day_low:.2f} - {day_high:.2f}"
                                }
                                
                                self.logger.info(f"Successfully got data for {ticker} using {period} timeframe")
                                break
                        except Exception as e:
                            self.logger.warning(f"Failed with {period} for {ticker}: {e}")
                            continue
                    
                    # If we get here and don't have data, use hardcoded fallback values
                    if ticker not in self.stock_data or 'price' not in self.stock_data[ticker]:
                        self.logger.warning(f"Using fallback data for {ticker}")
                        fallback_data = {
                            'AAPL': {'price': 205.76, 'percent_change': 0.22, 'volume': 54321000},
                            'GOOGL': {'price': 175.43, 'percent_change': -0.31, 'volume': 10293000},
                            'MSFT': {'price': 428.74, 'percent_change': 1.15, 'volume': 25678000},
                            'LLOY.L': {'price': 54.30, 'percent_change': 0.05, 'volume': 13456000}
                        }
                        
                        if ticker in fallback_data:
                            data = fallback_data[ticker]
                            self.stock_data[ticker] = {
                                'price': data['price'],
                                'percent_change': data['percent_change'],
                                'volume': data['volume'],
                                'day_range': f"{data['price']*0.99:.2f} - {data['price']*1.01:.2f}"
                            }
                        else:
                            # Still need a placeholder
                            self.stock_data[ticker] = {
                                'price': 100.00,  # Placeholder value
                                'percent_change': 0.0,
                                'volume': 0,
                                'day_range': 'N/A'
                            }
                except Exception as e:
                    self.logger.error(f"Complete failure fetching {ticker}: {e}")
                    # Add fallback data
                    self.stock_data[ticker] = {
                        'price': 100.00,  # Placeholder
                        'percent_change': 0.0,
                        'volume': 0,
                        'day_range': 'N/A'
                    }
                    
            self.logger.info("Stock data update complete")
            self.last_update = time.time()
        except Exception as e:
            self.logger.error(f"Fatal error updating stock data: {e}")



