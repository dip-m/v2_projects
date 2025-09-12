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

from typing import Optional, Tuple
import time, logging, os, json, math, random
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import time, logging
import pandas as pd
import yfinance as yf

try:
    import yfinance as yf  # type: ignore
except ImportError as e:
    raise ImportError(
        "yfinance is required for YahooPriceProvider. Install it with 'pip install yfinance'."
    ) from e


class YahooPriceProvider:
    # Disk cache inside the app data dir (persistent on Render)
    CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Throttle: min seconds between Yahoo calls
    MIN_INTERVAL = float(os.getenv("YF_MIN_INTERVAL", "1.2"))
    _last_call_ts = 0.0

    def _throttle(self):
        now = time.time()
        wait = self.MIN_INTERVAL - (now - self._last_call_ts)
        if wait > 0:
            time.sleep(wait)
        self._last_call_ts = time.time()

    def _retry(self, fn, attempts=3, base_delay=1.0):
        last = None
        for i in range(attempts):
            try:
                self._throttle()
                return fn()
            except Exception as e:
                last = e
                # Exponential backoff with jitter
                delay = base_delay * (2 ** i) + random.uniform(0, 0.5)
                logging.warning(f"Yahoo attempt {i+1}/{attempts} failed: {e} — backing off {delay:.1f}s")
                time.sleep(delay)
        if last:
            logging.error(f"Yahoo failed after {attempts} attempts: {last}")
        return None

    def _cache_path(self, kind: str, key: str) -> Path:
        safe = key.replace("/", "_").replace(":", "_")
        return self.CACHE_DIR / f"{kind}__{safe}"

    def _read_json_cache(self, path: Path, max_age: int) -> Optional[dict]:
        try:
            if not path.exists():
                return None
            age = time.time() - path.stat().st_mtime
            if age > max_age:
                return None
            return json.loads(path.read_text())
        except Exception:
            return None

    def _write_json_cache(self, path: Path, data: dict) -> None:
        try:
            path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    def _read_df_cache(self, path: Path, max_age: int) -> Optional[pd.DataFrame]:
        try:
            if not path.exists():
                return None
            age = time.time() - path.stat().st_mtime
            if age > max_age:
                return None
            if path.suffix == ".parquet":
                return pd.read_parquet(path)
            return pd.read_csv(path, parse_dates=True, index_col=0)
        except Exception:
            return None

    def _write_df_cache(self, path: Path, df: pd.DataFrame) -> None:
        try:
            if path.suffix == ".parquet":
                df.to_parquet(path, index=True)
            else:
                df.to_csv(path)
        except Exception:
            pass

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