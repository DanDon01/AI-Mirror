#!/usr/bin/env python
"""Visual test: StocksModule rendering in a standalone window (5 seconds)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import create_test_window, run_display_loop


def main():
    from stocks_module import StocksModule

    print("Testing StocksModule display (5 seconds)...")
    print("  Fetching stock data (may take a few seconds)...")
    print("  Press ESC or close window to exit early.")

    module = StocksModule(
        tickers=["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA", "AMD", "RR.L", "LLOY.L"],
    )

    module.update()
    fetched = len(getattr(module, "stock_data", {}))
    print(f"  {fetched} tickers loaded")

    screen, clock = create_test_window(400, 300, "Stocks Module Test")

    def draw(screen, elapsed):
        module.draw(screen, {"x": 20, "y": 10, "width": 360, "height": 280})

    run_display_loop(screen, clock, draw, duration_seconds=5)
    print("  Stocks display test complete.")


if __name__ == "__main__":
    main()
