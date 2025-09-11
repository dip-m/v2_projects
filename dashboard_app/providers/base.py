"""Provider interface definitions.

These protocols describe the minimal API expected from any price or
analyst data provider used by the dashboard. They allow you to plug
in alternative providers by implementing the same methods on your
provider class. See ``yahoo_prices.py`` and ``finnhub_analyst.py`` for
reference implementations.
"""

from __future__ import annotations

from typing import Protocol, Optional, Dict, Any
import pandas as pd


class PriceProvider(Protocol):
    """A price provider supplies recent market data for equities or ETFs.

    The ``recent_ohlc`` method should return a pandas DataFrame with
    columns ``['Open','High','Low','Close','Volume']`` indexed by
    timestamp. The ``latest_price`` method returns the most recent
    closing or last traded price for the given symbol.
    """

    def latest_price(self, symbol: str) -> Optional[float]:
        """Return the latest traded price for ``symbol`` or ``None`` if
        unavailable."""

    def recent_ohlc(self, symbol: str, period: str = "6mo", interval: str = "1d") -> Optional[pd.DataFrame]:
        """Return a DataFrame of historical OHLCV data."""


class AnalystProvider(Protocol):
    """An analyst provider supplies rating and price target information."""

    def recommendation(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Return analyst recommendation trends for ``symbol`` or ``None`` if unavailable.

        Implementations should return a dictionary like::

            {
              "as_of": "YYYY-MM",
              "counts": {"strongBuy": int, "buy": int, "hold": int, "sell": int, "strongSell": int},
              "percent": {"buy": float, "hold": float, "sell": float},
              "total": int
            }
        """

    def price_target(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Return price target statistics for ``symbol`` or ``None`` if unavailable.

        Expected return structure::

            {
              "avg_target": float,
              "median": float,
              "high": float,
              "low": float,
              "as_of": "YYYY-MM-DD"
            }
        """

    def next_earnings(self, symbol: str) -> Optional[str]:
        """Return the date of the next earnings report for the given symbol, if known.

        Implementations should return a string in ISO format (YYYY-MM-DD) representing
        the next earnings date. If no future earnings date is known, implementations may
        return the most recent past earnings date or ``None`` if unavailable.
        """