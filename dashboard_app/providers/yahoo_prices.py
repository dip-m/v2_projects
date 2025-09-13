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
import pandas as pd

"""
This module provides a thin wrapper around the optional ``yfinance`` package for
retrieving market data. In the original implementation, an ``ImportError`` was
raised at import time if ``yfinance`` could not be found. That behaviour made
the entire FastAPI application unusable in environments where outbound network
access is restricted and the dependency cannot be installed. To allow the rest
of the dashboard to function without live market data, the import of
``yfinance`` is now optional. When it is unavailable the provider methods
return ``None`` instead of throwing. This degrades gracefully: the UI still
lists tickers and buckets, albeit without live prices or indicators. If you
need real data simply install the ``yfinance`` package in your environment.
"""

try:
    # Attempt to import yfinance. If it is unavailable we fallback to a stub
    import yfinance as yf  # type: ignore
except Exception:
    yf = None  # type: ignore


class YahooPriceProvider:
    """Fetches price data from Yahoo Finance when available.

    If the optional ``yfinance`` dependency is missing, all methods will
    return ``None`` instead of raising an exception. This behaviour allows
    other parts of the dashboard to function without live market data.
    """

    def latest_price(self, symbol: str) -> Optional[float]:
        """
        Return the latest close or last traded price for ``symbol``.

        ``None`` is returned if the symbol is invalid, a fetch fails, or
        the ``yfinance`` dependency is unavailable. Note that Yahoo
        occasionally returns ``None`` for illiquid symbols or outside
        trading hours.
        """
        if yf is None:
            # yfinance not installed; return None gracefully
            return None
        try:
            ticker = yf.Ticker(symbol)
            # ``fast_info`` often contains the last price
            info = getattr(ticker, "fast_info", {}) or {}
            price = info.get("last_price")
            if price is None:
                # fallback to the most recent close
                hist = ticker.history(period="1d")
                if hist is None or hist.empty:
                    return None
                return float(hist["Close"].iloc[-1])
            return float(price)
        except Exception:
            return None

    def recent_ohlc(
        self,
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
    ) -> Optional[pd.DataFrame]:
        """
        Return a DataFrame of historical OHLCV data for ``symbol``.

        The DataFrame columns are ``Open``, ``High``, ``Low``, ``Close`` and
        ``Volume``. The index is a pandas ``DatetimeIndex``. ``None``
        indicates a fetch failure or missing ``yfinance``.
        """
        if yf is None:
            # Without yfinance we cannot fetch data
            return None
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval, auto_adjust=True)
            if df is None or df.empty:
                return None
            # Standardise column names capitalisation
            df = df.rename(columns=str.capitalize)
            return df
        except Exception:
            return None