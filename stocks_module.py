import yfinance as yf
import pygame
import logging
from datetime import datetime, timedelta
from pytz import timezone
from config import FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_PASTEL_GREEN, COLOR_PASTEL_RED, LINE_SPACING, TRANSPARENCY  # Import font settings and color constants from config

class StocksModule:
    def __init__(self, tickers, market_timezone='America/New_York'):
        self.tickers = tickers
        self.stock_data = {}
        try:
            self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE)
        except:
            print(f"Warning: Font '{FONT_NAME}' not found. Using default font.")
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
        self.status_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE - 16)

    def update(self):
        current_time = datetime.now(timezone('UTC'))
        
        if current_time - self.last_update < self.update_interval:
            return  # Skip update if not enough time has passed

        try:
            for ticker in self.tickers:
                market = 'UK' if ticker.endswith('.L') else 'US'
                current_market_time = current_time.astimezone(self.market_timezones[market])

                if not self.is_market_open(current_market_time, market):
                    logging.info(f"Market is closed for {ticker}. Displaying last available data.")
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
                    last_close = data['Close'].iloc[0]  # Last session's close
                    current_price = data['Close'].iloc[-1]  # Current price or last close
                    percent_change = ((current_price - last_close) / last_close) * 100
                    volume = data['Volume'].iloc[-1]
                    day_range = f"{data['Low'].min():.2f} - {data['High'].max():.2f}"
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
            self.last_update = current_time
            logging.info("Stock data updated successfully")
        except Exception as e:
            logging.error(f"Error updating stock data: {e}")

    def draw(self, screen, position):
        try:
            x, y = position
            current_time = datetime.now(timezone('UTC'))
            
            # Check market status
            us_open = self.is_market_open(current_time.astimezone(self.market_timezones['US']), 'US')
            uk_open = self.is_market_open(current_time.astimezone(self.market_timezones['UK']), 'UK')

            # Render text
            markets_text = self.markets_font.render("Markets:", True, COLOR_FONT_DEFAULT)
            us_status = "Open" if us_open else "Closed"
            uk_status = "Open" if uk_open else "Closed"
            us_text = self.status_font.render(f"US: {us_status}", True, COLOR_PASTEL_GREEN if us_open else COLOR_PASTEL_RED)
            uk_text = self.status_font.render(f"UK: {uk_status}", True, COLOR_PASTEL_GREEN if uk_open else COLOR_PASTEL_RED)

            # Set transparency
            markets_text.set_alpha(TRANSPARENCY)
            us_text.set_alpha(TRANSPARENCY)
            uk_text.set_alpha(TRANSPARENCY)

            # Calculate positions
            markets_width = markets_text.get_width()
            us_width = us_text.get_width()
            uk_width = uk_text.get_width()

            # Draw text
            screen.blit(markets_text, (x, y))
            screen.blit(us_text, (x + markets_width + 10, y - 4))
            screen.blit(uk_text, (x + markets_width + 10, y + 10))

            y += LINE_SPACING + 5  # Move position down after displaying market status

            # Draw alerts (now integrated into the main stock list)
            y = self.draw_alerts(screen, (x, y))

            # Draw stock data
            if self.stock_data:
                for ticker, data in self.stock_data.items():
                    price = data['price']
                    percent_change = data['percent_change']

                    color = COLOR_PASTEL_GREEN if isinstance(percent_change, float) and percent_change > 0 else COLOR_PASTEL_RED if isinstance(percent_change, float) and percent_change < 0 else COLOR_FONT_DEFAULT

                    currency_symbol = '£' if ticker.endswith('.L') else '$'

                    if percent_change != 'N/A':
                        text = f"{ticker}: {currency_symbol}{price:.2f} ({percent_change:+.2f}%)"
                    else:
                        text = f"{ticker}: {currency_symbol}{price:.2f}"

                    text_surface = self.font.render(text, True, color)
                    text_surface.set_alpha(TRANSPARENCY)
                    screen.blit(text_surface, (x, y))

                    y += LINE_SPACING  # Move to the next stock
            else:
                no_data_surface = self.font.render("Stock data unavailable", True, COLOR_PASTEL_RED)
                no_data_surface.set_alpha(TRANSPARENCY)
                screen.blit(no_data_surface, (x, y))

            # Draw scrolling ticker
            self.draw_scrolling_ticker(screen)

        except Exception as e:
            logging.error(f"Error drawing stock data: {e}")

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
                text = f"{ticker}: {currency_symbol}{price:.2f} {arrow} ({percent_change:+.2f}%)   "
            else:
                text = f"{ticker}: {currency_symbol}{price:.2f}   "

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
            logging.info(f"Displaying {len(self.alerts)} stock alerts")
            alert_font = pygame.font.SysFont(FONT_NAME, FONT_SIZE, bold=True)  # Use the same size as regular font, but bold
            for ticker, percent_change in self.alerts:
                color = COLOR_PASTEL_GREEN if percent_change > 0 else COLOR_PASTEL_RED
                text = f"{ticker} {percent_change:+.2f}%"
                text_surface = alert_font.render(text, True, color)
                text_surface.set_alpha(TRANSPARENCY)
                screen.blit(text_surface, (x, y))
                y += LINE_SPACING  # Move down for the next alert

        return y  # Return the new y position after drawing alerts

    def is_market_open(self, current_market_time, market):
        market_hours = self.market_hours[market]
        return market_hours['open'].time() <= current_market_time.time() < market_hours['close'].time()

    def cleanup(self):
        pass  # No cleanup needed for this module



