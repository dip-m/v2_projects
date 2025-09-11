"""Yahoo Finance price provider.

This provider uses the `yfinance` library to fetch historical and
latest price data from Yahoo Finance. It implements the
``PriceProvider`` protocol defined in ``providers/base.py``. You must
install the ``yfinance`` package in your environment (e.g. ``pip install yfinance``).

If you require intraday data or other intervals, adjust the
``interval`` argument of ``recent_ohlc`` accordingly. For example,
``interval='1h'`` returns hourly bars if available.
"""

from __future__ import annotations

from typing import Optional
import time, logging
import pandas as pd

try:
    import yfinance as yf  # type: ignore
except ImportError as e:
    raise ImportError(
        "yfinance is required for YahooPriceProvider. Install it with 'pip install yfinance'."
    ) from e


class YahooPriceProvider:
    def _retry(self, fn, attempts=3, delay=1.0):
        last_err = None
        for i in range(attempts):
            try:
                return fn()
            except Exception as e:
                last_err = e
                logging.warning(f"Yahoo retry {i+1}/{attempts} failed: {e}")
                time.sleep(delay)
        if last_err:
            logging.error(f"Yahoo fetch failed after {attempts} attempts: {last_err}")
        return None
    """Fetches price data from Yahoo Finance."""

    def latest_price(self, symbol: str) -> Optional[float]:
        """Return the latest close or last traded price for symbol.

        ``None`` is returned if the symbol is invalid or the request
        fails. Note that Yahoo occasionally returns ``None`` for
        illiquid symbols or outside trading hours.
        """
        try:
            ticker = yf.Ticker(symbol)
            # fast_info often contains the last price
            info = ticker.fast_info
            price = info.get("last_price")
            if price is None:
                # fallback to the most recent close
                hist = ticker.history(period="1d")
                if hist.empty:
                    return None
                return float(hist["Close"].iloc[-1])
            return float(price)
        except Exception:
            return None

    def recent_ohlc(self, symbol: str, period: str = "6mo", interval: str = "1d") -> Optional[pd.DataFrame]:
        """Return a DataFrame of historical OHLCV data.

        The DataFrame columns are ``Open``, ``High``, ``Low``, ``Close`` and
        ``Volume``. The index is pandas ``DatetimeIndex``. ``None``
        indicates a fetch failure.
        """
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval, auto_adjust=True)
            if df.empty:
                return None
            # Standardise column names capitalisation
            df = df.rename(columns=str.capitalize)
            return df
        except Exception:
            return None