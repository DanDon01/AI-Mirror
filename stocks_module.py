import yfinance as yf
import pygame
import logging
from datetime import datetime, timedelta
from pytz import timezone
from config import FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_PASTEL_GREEN, COLOR_PASTEL_RED, LINE_SPACING, TRANSPARENCY  # Import font settings and color constants from config
from visual_effects import VisualEffects
import time
import math

class StocksModule:
    def __init__(self, tickers, market_timezone='America/New_York'):
        self.tickers = tickers
        self.stock_data = {}
        try:
            self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE)
        except:
            print("Warning: Font '{}' not found. Using default font.".format(FONT_NAME))
            self.font = pygame.font.Font(None, FONT_SIZE)  # Fallback to default font
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
        self.scroll_speed = 2
        self.alerts = []

        self.markets_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE + 4)
        self.status_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE - 6)

        # Add new visual properties
        self.effects = VisualEffects()
        self.animation_start_time = time.time()
        self.item_fade_offsets = {ticker: i * 0.2 for i, ticker in enumerate(tickers)}
        self.header_pulse_speed = 0.3
        self.alert_pulse_speed = 0.8
        
        # Add background properties
        self.bg_color = (20, 20, 20)  # No alpha, handled in draw_rounded_rect
        self.header_bg_color = (40, 40, 40)  # No alpha, handled in draw_rounded_rect
        self.alert_bg_color = (60, 20, 20)  # No alpha, handled in draw_rounded_rect

    def update(self):
        """Update stock data with rate limiting protection"""
        # Use timezone-aware current_time
        current_time = datetime.now(timezone('UTC'))
        
        # Check if we need to update
        if current_time - self.last_update < self.update_interval:
            return
        
        try:
            if not hasattr(self, 'logger'):
                self.logger = logging.getLogger('stocks_module')
            
            # Check if we've already been rate-limited recently
            if hasattr(self, 'rate_limited') and self.rate_limited:
                time_since_rate_limit = time.time() - self.rate_limited_time
                if time_since_rate_limit < 3600:  # Wait an hour after being rate limited
                    self.logger.warning(f"Skipping Yahoo Finance API due to rate limiting (retry in {3600-time_since_rate_limit:.0f}s)")
                    return
            
            # Only test the connection once per day to avoid extra API calls
            day_now = datetime.now().day
            if not hasattr(self, 'last_test_day') or self.last_test_day != day_now:
                self.logger.info("Testing Yahoo Finance API connection...")
                self.last_test_day = day_now
                try:
                    # Use a bare minimum API call
                    test_ticker_obj = yf.Ticker("AAPL")
                    test_info = test_ticker_obj.fast_info
                    if test_info:
                        self.logger.info("✓ Yahoo Finance API working")
                        self.rate_limited = False
                except Exception as e:
                    if "429" in str(e) or "Too Many Requests" in str(e):
                        self.logger.warning("⚠ Yahoo Finance API rate limited")
                        self.rate_limited = True
                        self.rate_limited_time = time.time()
                        return
                    self.logger.error(f"✗ Yahoo Finance API test failed: {e}")
            
            # Update tickers if we're not rate limited
            if not getattr(self, 'rate_limited', False):
                for ticker in self.tickers:
                    self.update_ticker(ticker)
                    time.sleep(0.5)  # Add delay between requests to avoid rate limits
                
            self.last_update = current_time
            self.logger.info("Stock data update complete")
            
        except Exception as e:
            self.logger.error(f"Error updating stock data: {e}")

    def update_ticker(self, ticker):
        """Process a single ticker without fallback data"""
        try:
            # Get live data only
            stock = yf.Ticker(ticker)
            data = stock.history(period="2d")
            
            if not data.empty:
                # Successfully got data
                current_price = data['Close'].iloc[-1]
                if len(data) > 1:
                    previous_close = data['Close'].iloc[0]
                    percent_change = ((current_price - previous_close) / previous_close) * 100
                else:
                    percent_change = 0.0
                
                volume = data['Volume'].iloc[-1] if 'Volume' in data.columns else 0
                day_high = data['High'].max() if 'High' in data.columns else current_price
                day_low = data['Low'].min() if 'Low' in data.columns else current_price
                
                self.stock_data[ticker] = {
                    'price': current_price,
                    'percent_change': percent_change,
                    'volume': int(volume) if not math.isnan(volume) else 0,
                    'day_range': f"{day_low:.2f} - {day_high:.2f}"
                }
                if hasattr(self, 'logger'):
                    self.logger.info(f"✓ Live data for {ticker}: ${current_price:.2f}")
                return
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.warning(f"Failed to get data for {ticker}: {e}")
        
        # If we get here, no data was available
        self.stock_data[ticker] = {
            'price': 'N/A',
            'percent_change': 'N/A',
            'volume': 'N/A',
            'day_range': 'N/A'
        }
        if hasattr(self, 'logger'):
            self.logger.info(f"⚠ Data unavailable for {ticker}")

    def draw(self, screen, position):
        """Draw stock data with proper handling of unavailable data"""
        try:
            x, y = position if isinstance(position, tuple) else (position['x'], position['y'])
            
            # Check colors are valid RGB tuples before drawing
            if not (isinstance(self.bg_color, tuple) and len(self.bg_color) >= 3):
                self.bg_color = (20, 20, 20)
            if not (isinstance(self.header_bg_color, tuple) and len(self.header_bg_color) >= 3):
                self.header_bg_color = (40, 40, 40)
            
            # Draw module background
            module_rect = pygame.Rect(x-10, y-10, 280, 210)
            self.effects.draw_rounded_rect(screen, module_rect, self.bg_color, radius=15)
            
            # Draw header with pulsing effect
            header_rect = pygame.Rect(x-10, y-10, 280, 40)
            header_alpha = self.effects.pulse_effect(160, 220, self.header_pulse_speed)
            self.effects.draw_rounded_rect(screen, header_rect, self.header_bg_color, radius=15, alpha=header_alpha)
            
            # Draw title
            title_surface = self.effects.create_text_with_shadow(
                self.font, "STOCKS", COLOR_HEADER, offset=1)
            screen.blit(title_surface, (x + 10, y))
            
            # Check if all data is unavailable
            all_unavailable = all(
                isinstance(data.get('price'), str) and data.get('price') == 'N/A' 
                for data in self.stock_data.values()
            )
            
            if all_unavailable or not self.stock_data:
                # Draw unavailable message
                unavailable_text = self.font.render("Data Unavailable", True, COLOR_PASTEL_RED)
                screen.blit(unavailable_text, (x + 20, y + 60))
                return
            
            # Check market status with enhanced visuals
            current_time = datetime.now(timezone('UTC'))
            us_open = self.is_market_open(current_time.astimezone(self.market_timezones['US']), 'US')
            uk_open = self.is_market_open(current_time.astimezone(self.market_timezones['UK']), 'UK')
            
            # Create text with shadow effect
            markets_text = self.effects.create_text_with_shadow(
                self.markets_font, "Markets:", COLOR_FONT_DEFAULT, offset=1)
            
            us_status = "Open" if us_open else "Closed"
            uk_status = "Open" if uk_open else "Closed"
            
            us_text = self.effects.create_text_with_shadow(
                self.status_font, f"US: {us_status}", 
                COLOR_PASTEL_GREEN if us_open else COLOR_PASTEL_RED)
            
            uk_text = self.effects.create_text_with_shadow(
                self.status_font, f"UK: {uk_status}", 
                COLOR_PASTEL_GREEN if uk_open else COLOR_PASTEL_RED)
            
            # Draw text with fade-in effect
            screen.blit(markets_text, (x, y))
            screen.blit(us_text, (x + markets_text.get_width() + 10, y - 4))
            screen.blit(uk_text, (x + markets_text.get_width() + 10, y + 10))
            
            y += LINE_SPACING + 5  # Move position down after displaying market status
            
            # Draw alerts with pulsing effect
            y = self.draw_alerts(screen, (x, y))
            
            # Draw stock data with staggered fade-in
            if self.stock_data:
                for i, (ticker, data) in enumerate(self.stock_data.items()):
                    # Calculate fade-in alpha based on time offset
                    elapsed = time.time() - self.animation_start_time
                    fade_progress = min(1.0, max(0, elapsed - self.item_fade_offsets[ticker]))
                    alpha = int(220 * fade_progress)
                    
                    price = data['price']
                    percent_change = data['percent_change']
                    
                    # Fix here - handle 'N/A' properly
                    if isinstance(percent_change, str) and percent_change == 'N/A':
                        color = COLOR_FONT_DEFAULT
                    else:
                        # Determine color based on change
                        color = COLOR_PASTEL_GREEN if isinstance(percent_change, (float, int)) and percent_change > 0 else \
                              COLOR_PASTEL_RED if isinstance(percent_change, (float, int)) and percent_change < 0 else \
                              COLOR_FONT_DEFAULT
                    
                    currency_symbol = '£' if ticker.endswith('.L') else '$'
                    
                    # Format text with better spacing and alignment
                    if isinstance(price, (float, int)) and isinstance(percent_change, (float, int)):
                        ticker_text = f"{ticker}"
                        price_text = f"{currency_symbol}{price:.2f}"
                        change_text = f"({percent_change:+.2f}%)"
                        
                        # Create surfaces with shadow effect
                        ticker_surface = self.font.render(ticker_text, True, COLOR_FONT_DEFAULT)
                        price_surface = self.font.render(price_text, True, color)
                        change_surface = self.font.render(change_text, True, color)
                        
                        # Apply alpha fade
                        ticker_surface.set_alpha(alpha)
                        price_surface.set_alpha(alpha)
                        change_surface.set_alpha(alpha)
                        
                        # Position elements with better spacing
                        screen.blit(ticker_surface, (x, y))
                        screen.blit(price_surface, (x + 80, y))  # Adjust spacing as needed
                        screen.blit(change_surface, (x + 160, y))  # Adjust spacing as needed
                    else:
                        # Handle N/A values
                        price_str = f"{price:.2f}" if isinstance(price, (float, int)) else "N/A"
                        text = f"{ticker}: {currency_symbol}{price_str}"
                        text_surface = self.font.render(text, True, COLOR_FONT_DEFAULT)
                        text_surface.set_alpha(alpha)
                        screen.blit(text_surface, (x, y))
                    
                    y += LINE_SPACING  # Move to the next stock
            else:
                no_data_surface = self.font.render("Stock data unavailable", True, COLOR_PASTEL_RED)
                no_data_surface.set_alpha(TRANSPARENCY)
                screen.blit(no_data_surface, (x, y))
            
            # Draw scrolling ticker with enhanced visuals
            self.draw_scrolling_ticker(screen)
            
        except Exception as e:
            logging.error(f"Error drawing stock data: {e}", exc_info=True)  # Add exc_info to see full traceback

    def draw_scrolling_ticker(self, screen):
        ticker_height = 30
        y = screen.get_height() - ticker_height
        total_width = 0

        for ticker, data in self.stock_data.items():
            price = data['price'] 
            percent_change = data['percent_change']
            
            # Handle invalid values
            if isinstance(price, str) or price == 'N/A':
                continue
            
            if isinstance(percent_change, str) and percent_change == 'N/A':
                color = COLOR_FONT_DEFAULT
                arrow = ""
                percent_text = ""
            else:
                color = COLOR_PASTEL_GREEN if isinstance(percent_change, float) and percent_change > 0 else \
                       COLOR_PASTEL_RED if isinstance(percent_change, float) and percent_change < 0 else \
                       COLOR_FONT_DEFAULT
                arrow = "▲" if isinstance(percent_change, float) and percent_change > 0 else \
                       "▼" if isinstance(percent_change, float) and percent_change < 0 else ""
                percent_text = f" ({percent_change:+.2f}%)" if isinstance(percent_change, float) else ""

            currency_symbol = '£' if ticker.endswith('.L') else '$'
            
            # Safe formatting
            try:
                text = f"{ticker}: {currency_symbol}{price:.2f} {arrow}{percent_text}   "
                text_surface = self.ticker_font.render(text, True, color)
                text_surface.set_alpha(TRANSPARENCY)
                screen.blit(text_surface, (self.scroll_position + total_width, y))
                total_width += text_surface.get_width()
            except (ValueError, TypeError) as e:
                logging.error(f"Error rendering ticker {ticker}: {e}")
                continue

        self.scroll_position -= self.scroll_speed
        if self.scroll_position < -total_width:
            self.scroll_position = screen.get_width()

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



