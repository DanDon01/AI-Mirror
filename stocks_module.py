import yfinance as yf
import pygame
import logging
from datetime import datetime, timedelta
from pytz import timezone
from config import FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_PASTEL_GREEN, COLOR_PASTEL_RED, LINE_SPACING, TRANSPARENCY  # Import font settings and color constants from config
from visual_effects import VisualEffects
import time
import math

# Color constants
COLOR_HEADER = (240, 240, 240)  # White for headers

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
                self.logger.info("✓ Network connectivity confirmed")
            except Exception as e:
                self.logger.warning(f"⚠ Network issue: {e}")
                return
            
            # Update all tickers with batch fetching
            self.update_tickers_batch()
            
            self.last_update = current_time
            self.logger.info("Stock data update complete")
            
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
                        self.logger.warning("⚠ Yahoo Finance API rate limited")
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
                    self.logger.warning(f"⚠ Could not get data for {ticker}")
                    self.stock_data[ticker] = {'price': 'N/A', 'percent_change': 'N/A', 'volume': 'N/A', 'day_range': 'N/A'}
                    
                except Exception as e:
                    self.logger.error(f"✗ Error fetching {ticker}: {str(e)}")
                    self.stock_data[ticker] = {'price': 'N/A', 'percent_change': 'N/A', 'volume': 'N/A', 'day_range': 'N/A'}
                
                # Add delay between processing each ticker
                time.sleep(1.0)  # Longer delay to avoid rate limits
            
        except Exception as e:
            self.logger.error(f"Batch update failed: {e}")

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
            else:
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
        """Draw a scrolling ticker at the bottom of the screen with stock data"""
        try:
            ticker_height = 30
            y = screen.get_height() - ticker_height
            total_width = 0
            
            # Check if we have valid data
            if not self.stock_data or all(data.get('price') == 'N/A' for data in self.stock_data.values()):
                # Show "Market Closed" message instead of fake data
                message = "Markets Closed - Data Unavailable"
                text_surface = self.ticker_font.render(message, True, (200, 200, 200))
                text_surface.set_alpha(TRANSPARENCY)
                
                # Center the message
                x_pos = (screen.get_width() - text_surface.get_width()) // 2
                screen.blit(text_surface, (x_pos, y))
                return
            
            # If we have data, show the scrolling ticker
            for ticker, data in self.stock_data.items():
                price = data.get('price', 'N/A')
                percent_change = data.get('percent_change', 0)
                
                # Skip items with no valid price
                if price == 'N/A' or not isinstance(price, (int, float)):
                    continue
                
                # Format change as string with sign
                if isinstance(percent_change, (int, float)):
                    change_str = f"{'+' if percent_change >= 0 else ''}{percent_change:.2f}%"
                    arrow = "▲" if percent_change > 0 else "▼" if percent_change < 0 else ""
                    color = self.determine_color(percent_change)
                else:
                    change_str = "0.00%"
                    arrow = ""
                    color = (180, 180, 180)  # Default gray
                
                # Format with proper currency symbol
                currency_symbol = '£' if ticker.endswith('.L') else '$'
                text = f"{ticker}: {currency_symbol}{price:.2f} {arrow}{change_str}   "
                
                # Render and draw
                text_surface = self.ticker_font.render(text, True, color)
                text_surface.set_alpha(TRANSPARENCY)
                screen.blit(text_surface, (self.scroll_position + total_width, y))
                total_width += text_surface.get_width()
            
            # Scroll and reset position when needed
            self.scroll_position -= self.scroll_speed
            if self.scroll_position < -total_width:
                self.scroll_position = screen.get_width()
            
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



