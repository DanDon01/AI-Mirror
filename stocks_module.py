import yfinance as yf
import pygame
import logging
from datetime import datetime, timedelta
from pytz import timezone
from config import FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_PASTEL_GREEN, COLOR_PASTEL_RED, LINE_SPACING, TRANSPARENCY, CONFIG  # Import font settings and color constants from config
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
        """Draw stock data with consistent styling across modules"""
        try:
            # Extract position
            if isinstance(position, dict):
                x, y = position['x'], position['y']
            else:
                x, y = position
            
            # Get styling from config
            styling = CONFIG.get('module_styling', {})
            fonts = styling.get('fonts', {})
            backgrounds = styling.get('backgrounds', {})
            
            # Get styles for drawing
            radius = styling.get('radius', 15)
            padding = styling.get('spacing', {}).get('padding', 10)
            line_height = styling.get('spacing', {}).get('line_height', 22)
            
            # Initialize fonts if not already done
            if not hasattr(self, 'title_font'):
                title_size = fonts.get('title', {}).get('size', 24)
                body_size = fonts.get('body', {}).get('size', 16)
                small_size = fonts.get('small', {}).get('size', 14)
                
                self.title_font = pygame.font.SysFont(FONT_NAME, title_size)
                self.body_font = pygame.font.SysFont(FONT_NAME, body_size)
                self.small_font = pygame.font.SysFont(FONT_NAME, small_size)
            
            # Get background colors - Use transparent backgrounds 
            bg_color = (20, 20, 20, 100)  # Add alpha for transparency
            header_bg_color = (40, 40, 40, 120)  # Add alpha for transparency
            
            # Draw module background
            module_width = 225  # Reduced from 300 by 25%
            module_height = 200
            module_rect = pygame.Rect(x-padding, y-padding, module_width, module_height)
            header_rect = pygame.Rect(x-padding, y-padding, module_width, 40)
            
            try:
                # Draw background with rounded corners and transparency
                self.effects.draw_rounded_rect(screen, module_rect, bg_color, radius=radius, alpha=100)
                self.effects.draw_rounded_rect(screen, header_rect, header_bg_color, radius=radius, alpha=120)
            except:
                # Fallback if effects fail
                s = pygame.Surface((module_width, module_height), pygame.SRCALPHA)
                s.fill((20, 20, 20, 100))
                screen.blit(s, (x-padding, y-padding))
                
                s = pygame.Surface((module_width, 40), pygame.SRCALPHA)
                s.fill((40, 40, 40, 120))
                screen.blit(s, (x-padding, y-padding))
            
            # Draw title
            title_color = fonts.get('title', {}).get('color', (240, 240, 240))
            title_text = self.title_font.render("Stocks", True, title_color)
            screen.blit(title_text, (x + padding, y + padding))
            
            # Draw stock data
            current_y = y + 50  # Start below title
            
            if not self.stock_data:
                # No data available
                no_data_text = self.body_font.render("No stock data available", True, fonts.get('body', {}).get('color', (200, 200, 200)))
                screen.blit(no_data_text, (x + padding, current_y))
                return
            
            # Draw stock data in a grid
            col_width = 145
            row_height = 30
            
            # Display a subset of stocks in a grid layout
            stocks_to_display = list(self.stock_data.items())[:8]  # Limit to 8 stocks
            
            for i, (ticker, data) in enumerate(stocks_to_display):
                # Calculate position in grid (2 columns)
                col = i % 2
                row = i // 2
                
                item_x = x + padding + (col * col_width)
                item_y = current_y + (row * row_height)
                
                # Get price and change
                price = data.get('price', 'N/A')
                percent_change = data.get('percent_change', 0)
                
                # Determine color based on change
                if isinstance(percent_change, (int, float)):
                    color = self.determine_color(percent_change)
                    change_str = f"{'+' if percent_change >= 0 else ''}{percent_change:.2f}%"
                    arrow = "▲" if percent_change > 0 else "▼" if percent_change < 0 else ""
                else:
                    color = fonts.get('body', {}).get('color', (200, 200, 200))
                    change_str = "0.00%"
                    arrow = ""
                
                # Format with proper currency symbol
                currency_symbol = '£' if ticker.endswith('.L') else '$'
                
                # Draw ticker name
                ticker_text = self.body_font.render(ticker, True, fonts.get('body', {}).get('color', (200, 200, 200)))
                screen.blit(ticker_text, (item_x, item_y))
                
                # Draw price and change
                if isinstance(price, (int, float)):
                    price_text = self.small_font.render(f"{currency_symbol}{price:.2f}", True, color)
                    screen.blit(price_text, (item_x, item_y + 18))
                    
                    change_text = self.small_font.render(f"{arrow}{change_str}", True, color)
                    screen.blit(change_text, (item_x + 80, item_y + 18))
                else:
                    na_text = self.small_font.render("N/A", True, fonts.get('small', {}).get('color', (180, 180, 180)))
                    screen.blit(na_text, (item_x, item_y + 18))
                
        except Exception as e:
            logging.error(f"Error drawing stocks: {e}")
            logging.error(traceback.format_exc())

    def draw_scrolling_ticker(self, screen):
        """Draw a scrolling ticker at the bottom of the screen with stock data"""
        try:
            ticker_height = 30
            y = screen.get_height() - ticker_height
            screen_width = screen.get_width()
            total_width = 0
            
            # Check if we have valid data
            if not self.stock_data or all(data.get('price') == 'N/A' for data in self.stock_data.values()):
                # Show "Market Closed" message instead of fake data
                message = "Markets Closed - Data Unavailable"
                text_surface = self.ticker_font.render(message, True, (200, 200, 200))
                text_surface.set_alpha(TRANSPARENCY)
                
                # Center the message
                x_pos = (screen_width - text_surface.get_width()) // 2
                screen.blit(text_surface, (x_pos, y))
                return
            
            # Create a list of rendered ticker items first to get total width
            ticker_items = []
            
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
                
                # Render text
                text_surface = self.ticker_font.render(text, True, color)
                text_surface.set_alpha(TRANSPARENCY)
                ticker_items.append((text_surface, color))
                total_width += text_surface.get_width()
            
            # If no valid items, return
            if not ticker_items:
                return
            
            # Draw all ticker items
            current_x = self.scroll_position
            
            # Draw items until we fill the screen width
            for text_surface, _ in ticker_items:
                # Only draw if at least partially on screen
                if current_x + text_surface.get_width() > 0 and current_x < screen_width:
                    screen.blit(text_surface, (current_x, y))
                current_x += text_surface.get_width()
                
                # If we've gone through all items but haven't filled the screen, repeat from the beginning
                if current_x < screen_width and len(ticker_items) > 0:
                    for repeat_surface, _ in ticker_items:
                        screen.blit(repeat_surface, (current_x, y))
                        current_x += repeat_surface.get_width()
                        if current_x > screen_width:
                            break
            
            # Scroll and reset position when needed
            self.scroll_position -= self.scroll_speed
            if self.scroll_position < -total_width:
                self.scroll_position = screen_width
            
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



