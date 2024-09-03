import yfinance as yf
import pygame
import logging
from datetime import datetime, timedelta
from pytz import timezone
from config import FONT_NAME, FONT_SIZE, COLOR_FONT_DEFAULT, COLOR_PASTEL_GREEN, COLOR_PASTEL_RED  # Import font settings and color constants from config

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
        self.update_interval = timedelta(minutes=15)
        
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

            us_status_text = "US Market: OPEN" if us_open else "US Market: CLOSED"
            uk_status_text = "UK Market: OPEN" if uk_open else "UK Market: CLOSED"

            # When rendering text, use the new color constants
            us_status_surface = self.font.render(us_status_text, True, COLOR_PASTEL_GREEN if us_open else COLOR_PASTEL_RED)
            uk_status_surface = self.font.render(uk_status_text, True, COLOR_PASTEL_GREEN if uk_open else COLOR_PASTEL_RED)
            screen.blit(us_status_surface, (x, y))
            screen.blit(uk_status_surface, (x, y + 25))

            y += 60  # Move position down after displaying market status

            # Draw stock data
            for ticker, data in self.stock_data.items():
                price = data['price']
                percent_change = data['percent_change']
                volume = data['volume']
                day_range = data['day_range']

                # Determine color based on percent change
                color = COLOR_PASTEL_GREEN if isinstance(percent_change, float) and percent_change > 0 else COLOR_PASTEL_RED if isinstance(percent_change, float) and percent_change < 0 else COLOR_FONT_DEFAULT

                text = f"{ticker}: ${price:.2f} ({percent_change:+.2f}%)" if percent_change != 'N/A' else f"{ticker}: ${price:.2f}"
                text_surface = self.font.render(text, True, color)
                screen.blit(text_surface, (x, y))

                details_text = f"Vol: {volume} | Range: {day_range}"
                details_surface = self.font.render(details_text, True, COLOR_FONT_DEFAULT)
                screen.blit(details_surface, (x, y + 25))

                y += 60  # Move to the next stock
        except Exception as e:
            logging.error(f"Error drawing stock data: {e}")
            error_surface = self.font.render("Stock data unavailable", True, (255, 0, 0))
            screen.blit(error_surface, position)

    def is_market_open(self, current_market_time, market):
        market_hours = self.market_hours[market]
        return market_hours['open'].time() <= current_market_time.time() < market_hours['close'].time()

    def cleanup(self):
        pass  # No cleanup needed for this module



