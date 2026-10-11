#!/usr/bin/env python
"""Test yfinance stock data fetching."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import run_test, TestResult


TICKERS = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA", "AMD", "RR.L", "LLOY.L"]


def test_single_ticker():
    import yfinance as yf

    ticker = yf.Ticker("AAPL")
    info = ticker.fast_info
    price = info.get("lastPrice") or info.get("last_price")
    if price is None:
        # Try history fallback
        hist = ticker.history(period="1d")
        if hist.empty:
            return False, "no price data for AAPL"
        price = hist["Close"].iloc[-1]
    return True, f"AAPL: ${price:.2f}"


def test_batch_fetch():
    import yfinance as yf

    data = yf.download(TICKERS, period="1d", group_by="ticker", progress=False)
    if data.empty:
        return False, "batch download returned empty"

    fetched = []
    for t in TICKERS:
        try:
            if t in data.columns.get_level_values(0):
                close = data[t]["Close"].iloc[-1]
                if close > 0:
                    fetched.append(t)
        except Exception:
            pass

    return len(fetched) > 0, f"{len(fetched)}/{len(TICKERS)} tickers returned data"


def test_uk_market():
    import yfinance as yf

    ticker = yf.Ticker("LLOY.L")
    hist = ticker.history(period="5d")
    if hist.empty:
        return False, "no data for LLOY.L (Lloyds Banking)"
    price = hist["Close"].iloc[-1]
    return True, f"LLOY.L: {price:.2f}p"


def main():
    results = TestResult()

    print("Testing yfinance API...")
    print("-" * 50)

    run_test("Single ticker (AAPL)", test_single_ticker, results)
    run_test("Batch fetch (8 tickers)", test_batch_fetch, results)
    run_test("UK market (LLOY.L)", test_uk_market, results)

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
