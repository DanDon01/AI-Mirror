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
        self.bg_color = (20, 20, 20, 180)  # Dark with transparency
        self.header_bg_color = (40, 40, 40, 200)
        self.alert_bg_color = (60, 20, 20, 200)  # Reddish for alerts

    def update(self):
        current_time = datetime.now(timezone('UTC'))
        
        if current_time - self.last_update < self.update_interval:
            if not hasattr(self, 'last_skip_log') or current_time - self.last_skip_log > timedelta(minutes=5):
                logging.debug("Skipping stock update: Not enough time has passed since last update")
                self.last_skip_log = current_time
            return  # Skip update if not enough time has passed

        try:
            for ticker in self.tickers:
                market = 'UK' if ticker.endswith('.L') else 'US'
                current_market_time = current_time.astimezone(self.market_timezones[market])

                logging.info("Updating %s stock: %s", market, ticker)
                logging.info("Current market time: %s", current_market_time)
                logging.info("Market open: %s", self.is_market_open(current_market_time, market))

                if not self.is_market_open(current_market_time, market):
                    logging.info("Market is closed for %s. Displaying last available data.", ticker)
                    # Fetching last available data (closing prices from the previous session)
                    stock = yf.Ticker(ticker)
                    data = stock.history(period="1d")
                    if not data.empty:
                        last_close = data['Close'].iloc[-1]
                        self.stock_data[ticker] = {
                            'price': last_close,
                            'percent_change': 'N/A',
                            'volume': 'N/A',
                            'day_range': 'N/A'
                        }
                    continue

                # Fetch real-time data if the market is open
                stock = yf.Ticker(ticker)
                data = stock.history(period="1d", interval="1m")
                if not data.empty:
                    last_close = float(data['Close'].iloc[0])  # Last session's close
                    current_price = float(data['Close'].iloc[-1])  # Current price or last close
                    percent_change = ((current_price - last_close) / last_close) * 100
                    volume = int(data['Volume'].iloc[-1])
                    day_range = "{:.2f} - {:.2f}".format(float(data['Low'].min()), float(data['High'].max()))
                    self.stock_data[ticker] = {
                        'price': current_price,
                        'percent_change': percent_change,
                        'volume': volume,
                        'day_range': day_range
                    }
                else:
                    self.stock_data[ticker] = {
                        'price': 'N/A',
                        'percent_change': 'N/A',
                        'volume': 'N/A',
                        'day_range': 'N/A'
                    }
                logging.info("Updated data for %s: %s", ticker, self.stock_data[ticker])
            self.last_update = current_time
            logging.info("Stock data updated successfully")
        except Exception as e:
            logging.error("Error updating stock data: %s", e)

    def draw(self, screen, position):
        try:
            x, y = position
            current_time = datetime.now(timezone('UTC'))
            
            # Create a background surface for the entire module
            module_width = 300  # Adjust based on your layout
            module_height = (len(self.tickers) + 4) * LINE_SPACING  # Height based on content
            
            # Draw module background
            module_rect = pygame.Rect(x-10, y-10, module_width, module_height)
            self.effects.draw_rounded_rect(screen, module_rect, self.bg_color, radius=15, alpha=180)
            
            # Draw header with pulsing effect
            header_rect = pygame.Rect(x-10, y-10, module_width, LINE_SPACING + 10)
            header_alpha = self.effects.pulse_effect(180, 220, self.header_pulse_speed)
            self.effects.draw_rounded_rect(screen, header_rect, self.header_bg_color, radius=15, alpha=header_alpha)
            
            # Check market status with enhanced visuals
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
                        text = f"{ticker}: N/A"
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
            logging.error(f"Error drawing stock data: {str(e)}")

    def draw_scrolling_ticker(self, screen):
        ticker_height = 30
        y = screen.get_height() - ticker_height
        total_width = 0

        for ticker, data in self.stock_data.items():
            price = data['price']
            percent_change = data['percent_change']

            color = COLOR_PASTEL_GREEN if isinstance(percent_change, float) and percent_change > 0 else COLOR_PASTEL_RED if isinstance(percent_change, float) and percent_change < 0 else COLOR_FONT_DEFAULT

            currency_symbol = '£' if ticker.endswith('.L') else '$'
            arrow = "▲" if isinstance(percent_change, float) and percent_change > 0 else "▼" if isinstance(percent_change, float) and percent_change < 0 else ""

            if percent_change != 'N/A':
                text = "{}: {}{:.2f} {} ({:+.2f}%)   ".format(ticker, currency_symbol, price, arrow, percent_change)
            else:
                text = "{}: {}{:.2f}   ".format(ticker, currency_symbol, price)

            text_surface = self.ticker_font.render(text, True, color)
            text_surface.set_alpha(TRANSPARENCY)
            screen.blit(text_surface, (self.scroll_position + total_width, y))
            total_width += text_surface.get_width()

        self.scroll_position -= self.scroll_speed
        if self.scroll_position < -total_width:
            self.scroll_position = screen.get_width()
            logging.info("Stock ticker reset position")  # Log only when resetting position

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



