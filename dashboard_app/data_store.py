"""Central data store for the dashboard.

This module defines the DataStore class, which holds ticker metadata,
bucket allocations and generates signals based on real market data. It
uses a price provider (``YahooPriceProvider``) and an optional
analyst provider (``FinnhubAnalystProvider``) to pull data. Buckets
are dynamic; you can create, rename and delete buckets at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from pathlib import Path
import os
import json
from datetime import datetime
from datetime import date as _date

# Optional import for Yahoo earnings fallback. If yfinance is unavailable, the fallback will be disabled.
try:
    import yfinance as _yf  # type: ignore
except Exception:  # pragma: no cover
    _yf = None  # type: ignore


def _yahoo_next_earnings_fallback(symbol: str) -> Optional[str]:
    """Best-effort fallback using Yahoo Finance to determine the next earnings date.

    This helper is used when the configured analyst provider does not return an earnings date.
    It tries to fetch earnings dates from the Yahoo Finance calendar or earnings dates API.
    Returns a date string in ISO format (YYYY-MM-DD) or None if unavailable.
    """
    if _yf is None:
        return None
    try:
        t = _yf.Ticker(symbol)
        candidates: List[str] = []
        # Helper to normalize a value into ISO date
        def _to_date(val: Any) -> Optional[str]:
            from datetime import datetime, date
            try:
                if hasattr(val, "to_pydatetime"):
                    return val.to_pydatetime().date().isoformat()  # type: ignore[attr-defined]
                if isinstance(val, (int, float)):
                    return datetime.utcfromtimestamp(float(val)).date().isoformat()
                if isinstance(val, str):
                    s = val.split()[0]
                    return datetime.fromisoformat(s).date().isoformat()
                if isinstance(val, (list, tuple)) and val:
                    return _to_date(val[0])
            except Exception:
                return None
            return None
        # 1) Try calendar via get_calendar() or calendar property
        try:
            cal_fn = getattr(t, "get_calendar", None)
            cdf = cal_fn() if callable(cal_fn) else getattr(t, "calendar", None)
            if cdf is not None and hasattr(cdf, "index"):
                for key in [
                    "Earnings Date", "EarningsDate",
                    "Earnings Date Start", "Earnings Date End",
                    "Earnings Date Estimate",
                ]:
                    if key in cdf.index:
                        val = cdf.loc[key]
                        try:
                            seq = val.values if hasattr(val, "values") else [val]
                        except Exception:
                            seq = [val]
                        for v in (seq if isinstance(seq, (list, tuple)) else [seq]):
                            d = _to_date(v)
                            if d:
                                candidates.append(d)
            # If we already have candidates, proceed to selection
        except Exception:
            pass
        # 2) If no candidates yet, use get_earnings_dates(limit=40)
        if not candidates:
            try:
                df = t.get_earnings_dates(limit=40)
                if df is not None and hasattr(df, "index"):
                    for ts in df.index:
                        d = _to_date(ts)
                        if d:
                            candidates.append(d)
            except Exception:
                pass
        if not candidates:
            return None
        # Choose the first future date if available; otherwise the latest past date
        from datetime import date
        today = date.today().isoformat()
        fut = sorted([d for d in candidates if d >= today])
        return fut[0] if fut else sorted(candidates)[-1]
    except Exception:
        return None
import pandas as pd

from .providers.yahoo_prices import YahooPriceProvider
from .providers.finnhub_analyst import FinnhubAnalystProvider
from .security.id_map import resolve_security


@dataclass
class TickerMeta:
    symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    isin: Optional[str] = None
    wkn: Optional[str] = None
    type: str = "equity"  # or 'etf'
    active: bool = True


@dataclass
class SignalRow:
    symbol: str
    bucket: str
    close: Optional[float]
    sma50: Optional[float]
    sma200: Optional[float]
    above50: bool
    above200: bool
    entry_ok: bool
    # Added indicators
    delta_sma50_pct: Optional[float] = None
    delta_sma200_pct: Optional[float] = None
    rsi14: Optional[float] = None
    rsi_zone: Optional[str] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    w52_high: Optional[float] = None
    w52_low: Optional[float] = None
    pct_to_52w_high: Optional[float] = None
    pct_from_52w_low: Optional[float] = None
    pivot: Optional[float] = None
    vol_avg20_ratio: Optional[float] = None
    reentry: Optional[bool] = None


class DataStore:
    """A simple, in-memory data store.

    This store maintains a set of tickers and their bucket assignments.
    It fetches real price data via ``YahooPriceProvider`` and computes
    moving averages and entry signals. Analyst information can be
    obtained via a ``FinnhubAnalystProvider`` if configured.
    """

    def __init__(self) -> None:
        # Tickers keyed by symbol. The keys are uppercase. Values are
        # ``TickerMeta`` describing the instrument.
        # Storage paths for persistence
        data_dir = Path(__file__).resolve().parent / "data"
        data_dir.mkdir(exist_ok=True)
        self._state_file = data_dir / "state.json"

        # Price provider (Yahoo). Replace with your own provider if desired.
        self._price = YahooPriceProvider()
        # Optional analyst provider. If no key is configured, calls return None.
        self._analyst = FinnhubAnalystProvider(os.getenv("FINNHUB_API_KEY"))
        # Cache for breadth calculation to avoid recomputation within a call
        self._breadth_cache: Optional[bool] = None
        # Cache for analyst data to avoid hitting provider too often
        self._analyst_cache: Dict[str, Dict[str, Any]] = {}
        # Tickers keyed by symbol. The keys are uppercase. Values are
        # ``TickerMeta`` describing the instrument.
        self._tickers: Dict[str, TickerMeta] = {}
        # Buckets mapping bucket_name -> list of ticker symbols
        self._buckets: Dict[str, List[str]] = {}
        # Load persisted state if available, otherwise bootstrap
        if self._state_file.exists():
            self._load_state()
        else:
            # default buckets
            self._buckets = {
                "conviction": [],
                "swing": [],
                "premium": [],
                "avoid": [],
            }
            self.bootstrap()
            self._save_state()

    # ----- Bucket operations -----
    def create_bucket(self, name: str) -> None:
        key = name.strip().lower()
        if key not in self._buckets:
            self._buckets[key] = []
            self._save_state()

    def rename_bucket(self, old: str, new: str) -> None:
        oldk = old.strip().lower()
        newk = new.strip().lower()
        if oldk not in self._buckets:
            raise ValueError(f"Bucket '{old}' does not exist")
        if newk in self._buckets:
            raise ValueError(f"Bucket '{new}' already exists")
        self._buckets[newk] = self._buckets.pop(oldk)
        self._save_state()

    def delete_bucket(self, name: str) -> None:
        key = name.strip().lower()
        if key in self._buckets:
            # Move any tickers to 'avoid' if deletion occurs
            moved = self._buckets.pop(key)
            self._buckets.setdefault("avoid", []).extend(moved)
            self._save_state()

    # ----- Ticker management -----
    def add_ticker(self, symbol_or_id: str, bucket: Optional[str] = None, type_hint: Optional[str] = None) -> None:
        resolved = resolve_security(symbol_or_id)
        if resolved is None:
            raise ValueError(f"Unknown symbol/ISIN/WKN: {symbol_or_id}")
        sym = resolved.upper()
        if sym not in self._tickers:
            typ = type_hint or ("etf" if any(ext in sym for ext in [".DE", ".L", ".HK", ".SW"]) else "equity")
            self._tickers[sym] = TickerMeta(symbol=sym, type=typ)
        # assign to bucket
        target = (bucket or "swing").strip().lower()
        if target not in self._buckets:
            self.create_bucket(target)
        # ensure symbol appears only in one bucket
        for lst in self._buckets.values():
            if sym in lst:
                lst.remove(sym)
        self._buckets[target].append(sym)
        # clear breadth cache as membership changed
        self._breadth_cache = None
        self._save_state()

    def remove_ticker(self, symbol: str) -> None:
        sym = symbol.upper()
        self._tickers.pop(sym, None)
        for lst in self._buckets.values():
            if sym in lst:
                lst.remove(sym)
        self._breadth_cache = None
        self._save_state()

    def move_ticker(self, symbol: str, bucket: str) -> None:
        sym = symbol.upper()
        if sym not in self._tickers:
            return
        target = bucket.strip().lower()
        if target not in self._buckets:
            self.create_bucket(target)
        for lst in self._buckets.values():
            if sym in lst:
                lst.remove(sym)
        self._buckets[target].append(sym)
        self._breadth_cache = None
        self._save_state()

    # ----- Signal calculations -----
    def _sma(self, series: pd.Series, window: int) -> Optional[float]:
        if series is None or len(series) < window:
            return None
        return float(series.tail(window).mean())

    
    def _ema(self, series: "pd.Series", span: int) -> Optional[float]:
        try:
            return float(series.ewm(span=span, adjust=False).mean().iloc[-1])
        except Exception:
            return None

    def _rsi(self, series: "pd.Series", period: int = 14) -> Optional[float]:
        try:
            delta = series.diff()
            gains = delta.clip(lower=0).rolling(window=period).mean()
            losses = (-delta.clip(upper=0)).rolling(window=period).mean()
            rs = gains / (losses.replace(0, 1e-9))
            rsi = 100 - (100 / (1 + rs))
            val = float(rsi.iloc[-1])
            if val < 0 or val > 100:
                return None
            return round(val, 2)
        except Exception:
            return None

    def _macd(self, series: "pd.Series", fast: int = 12, slow: int = 26, signal: int = 9):
        try:
            ema_fast = series.ewm(span=fast, adjust=False).mean()
            ema_slow = series.ewm(span=slow, adjust=False).mean()
            macd = ema_fast - ema_slow
            macd_signal = macd.ewm(span=signal, adjust=False).mean()
            macd_hist = macd - macd_signal
            return float(macd.iloc[-1]), float(macd_signal.iloc[-1]), float(macd_hist.iloc[-1])
        except Exception:
            return None, None, None

    def _classic_pivot(self, prev_high: float, prev_low: float, prev_close: float) -> Optional[float]:
        try:
            return round((prev_high + prev_low + prev_close) / 3.0, 2)
        except Exception:
            return None
    
    def _hist(self, symbol: str) -> Optional[pd.DataFrame]:
        return self._price.recent_ohlc(symbol, period="12mo", interval="1d")

    
    def _calc_signal(self, symbol: str, bucket: str) -> SignalRow:
        df = self._hist(symbol)
        if df is None or df.empty:
            return SignalRow(
                symbol=symbol, bucket=bucket,
                close=None, sma50=None, sma200=None,
                above50=False, above200=False, entry_ok=False
            )
        # Ensure standardized column names
        try:
            df = df.rename(columns=str.capitalize)
        except Exception:
            pass
        close = float(df["Close"].iloc[-1])
        # Moving averages
        sma50 = self._sma(df["Close"], 50)
        sma200 = self._sma(df["Close"], 200)
        above50 = close > (sma50 if sma50 is not None else -1e18)
        above200 = close > (sma200 if sma200 is not None else -1e18)
        entry_ok = bool(above50 and above200 and self.risk_on())
        # Deltas to SMAs
        delta_sma50_pct = round(((close / sma50) - 1) * 100, 2) if sma50 is not None else None
        delta_sma200_pct = round(((close / sma200) - 1) * 100, 2) if sma200 is not None else None
        # RSI
        rsi14 = self._rsi(df["Close"], 14)
        rsi_zone = ('Overbought' if (rsi14 is not None and rsi14 >= 70) else
                    ('Oversold' if (rsi14 is not None and rsi14 <= 30) else
                     ('Neutral' if rsi14 is not None else None)))
        # MACD
        macd, macd_signal, macd_hist = self._macd(df["Close"])
        # 52-week window (approx 252 trading days)
        window = min(len(df), 252)
        w52_high = float(df['High'].tail(window).max()) if window > 0 else None
        w52_low = float(df['Low'].tail(window).min()) if window > 0 else None
        pct_to_52w_high = round(((w52_high / close) - 1) * 100, 2) if (w52_high is not None and close is not None) else None
        pct_from_52w_low = round(((close / w52_low) - 1) * 100, 2) if (w52_low is not None and close is not None) else None
        # Classic pivot from previous day
        if len(df) >= 2:
            prev = df.iloc[-2]
            pivot = self._classic_pivot(float(prev["High"]), float(prev["Low"]), float(prev["Close"]))
        else:
            pivot = None
        # Volume ratio
        try:
            vol_avg20 = float(df["Volume"].rolling(window=20).mean().iloc[-1])
            vol_last = float(df["Volume"].iloc[-1])
            vol_avg20_ratio = round((vol_last / vol_avg20), 2) if (vol_avg20 and vol_avg20 != 0) else None
        except Exception:
            vol_avg20_ratio = None
        # Re-entry: crossed above SMA50 today after being below yesterday
        try:
            if len(df) >= 2 and sma50 is not None:
                y_close = float(df["Close"].iloc[-2])
                reentry = (y_close < sma50) and (close > sma50)
            else:
                reentry = None
        except Exception:
            reentry = None
        return SignalRow(
            symbol=symbol, bucket=bucket,
            close=close, sma50=sma50, sma200=sma200,
            above50=above50, above200=above200, entry_ok=entry_ok,
            delta_sma50_pct=delta_sma50_pct, delta_sma200_pct=delta_sma200_pct,
            rsi14=rsi14, rsi_zone=rsi_zone,
            macd=(round(macd, 4) if isinstance(macd, (int, float)) else macd),
            macd_signal=(round(macd_signal, 4) if isinstance(macd_signal, (int, float)) else macd_signal),
            macd_hist=(round(macd_hist, 4) if isinstance(macd_hist, (int, float)) else macd_hist),
            w52_high=(round(w52_high, 2) if isinstance(w52_high, (int, float)) else w52_high),
            w52_low=(round(w52_low, 2) if isinstance(w52_low, (int, float)) else w52_low),
            pct_to_52w_high=pct_to_52w_high,
            pct_from_52w_low=pct_from_52w_low,
            pivot=(round(pivot, 2) if isinstance(pivot, (int, float)) else pivot),
            vol_avg20_ratio=vol_avg20_ratio,
            reentry=reentry
        )
# ----- State persistence -----
    def _save_state(self) -> None:
        """Persist current tickers and bucket allocations to disk."""
        try:
            payload: Dict[str, Any] = {
                "buckets": self._buckets,
                "tickers": {sym: vars(meta) for sym, meta in self._tickers.items()},
            }
            with self._state_file.open("w") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            # If persistence fails, silently ignore; next run will start from bootstrap
            pass

    def _load_state(self) -> None:
        """Load persisted tickers and buckets from disk."""
        try:
            with self._state_file.open() as f:
                data = json.load(f)
            self._buckets = {k: list(v) for k, v in data.get("buckets", {}).items()}
            self._tickers = {}
            for sym, meta in data.get("tickers", {}).items():
                # reconstruct TickerMeta
                tm = TickerMeta(**meta)
                self._tickers[sym] = tm
        except Exception:
            # On error, fall back to default bootstrap
            self._buckets = {
                "conviction": [],
                "swing": [],
                "premium": [],
                "avoid": [],
            }
            self._tickers = {}

    # ----- Analyst helper -----
    def _analyst_maybe(self, symbol: str) -> Dict[str, Any]:
        """Return analyst summary for a symbol (avg target, buy/hold/sell %, total analysts) or blanks.

        This helper fetches analyst recommendation and price target data using the configured
        analyst provider. If no provider is configured, or no data is available for the symbol,
        it returns a dictionary with ``None`` for all fields. Results are cached for up to 60
        minutes to avoid repeated API calls.
        """
        # If no provider is configured, return blank fields immediately.
        if self._analyst is None:
            return {
                "avg_target": None,
                "buy_pct": None,
                "hold_pct": None,
                "sell_pct": None,
                "analyst_total": None,
            }
        now = datetime.utcnow()
        # Check cache (TTL: 60 minutes)
        cached = self._analyst_cache.get(symbol)
        if cached:
            try:
                ts = datetime.fromisoformat(cached.get("_ts", ""))
                if (now - ts).total_seconds() <= 3600:
                    return {k: cached.get(k) for k in ["avg_target", "buy_pct", "hold_pct", "sell_pct", "analyst_total"]}
            except Exception:
                pass
        # Fetch recommendation and price target data
        rec = self._analyst.recommendation(symbol) or {}
        pt = self._analyst.price_target(symbol) or {}
        avg_target = pt.get("avg_target") or pt.get("targetMean")
        # Extract percentage breakdowns from recommendation
        perc = rec.get("percent") or {}
        buy_pct = perc.get("buy")
        hold_pct = perc.get("hold")
        sell_pct = perc.get("sell")
        total = rec.get("total")
        counts = rec.get("counts") or {}

        # Derive total analysts if not provided but counts exist
        if (not total or total == 0) and counts:
            try:
                total = int(sum(int(counts.get(k, 0)) for k in [
                    "strongBuy", "buy", "hold", "sell", "strongSell"]))
            except Exception:
                total = None

        # Derive percentages if missing but counts and total are available
        if ((buy_pct is None and hold_pct is None and sell_pct is None) or not perc) and counts and total:
            try:
                sb = int(counts.get("strongBuy", 0) or 0)
                b  = int(counts.get("buy", 0) or 0)
                h  = int(counts.get("hold", 0) or 0)
                s  = int(counts.get("sell", 0) or 0)
                ss = int(counts.get("strongSell", 0) or 0)
                # Compute percentages
                buy_pct  = 100.0 * (sb + b) / total if total else None
                hold_pct = 100.0 * h / total if total else None
                sell_pct = 100.0 * (s + ss) / total if total else None
            except Exception:
                buy_pct = hold_pct = sell_pct = None
        # Helper to round floats to two decimals
        def r2(x: Any) -> Optional[float]:
            return None if x is None else round(float(x), 2)
        payload = {
            "avg_target": r2(avg_target),
            "buy_pct": r2(buy_pct),
            "hold_pct": r2(hold_pct),
            "sell_pct": r2(sell_pct),
            "analyst_total": total,
            "_ts": now.isoformat(),
        }
        # Cache the payload
        self._analyst_cache[symbol] = payload
        return {k: payload.get(k) for k in ["avg_target", "buy_pct", "hold_pct", "sell_pct", "analyst_total"]}

    def signals(self, include_analyst: bool = True) -> List[Dict[str, Any]]:
        """Return a list of signal dictionaries for all tickers.

        Each dictionary contains symbol, bucket, close, SMA50, SMA200,
        boolean flags for above50/above200, entry_ok, and if
        include_analyst is True, also includes avg_target, buy_pct,
        hold_pct, sell_pct, analyst_total, and dist_to_target_pct.
        Numeric values are rounded to two decimals or None.
        """
        out: List[Dict[str, Any]] = []
        for bucket, syms in self._buckets.items():
            for sym in syms:
                row = self._calc_signal(sym, bucket)
                # base fields with rounding
                d: Dict[str, Any] = {
                    "symbol": row.symbol,
                    "bucket": row.bucket,
                    "close": None if row.close is None else round(row.close, 2),
                    "sma50": None if row.sma50 is None else round(row.sma50, 2),
                    "sma200": None if row.sma200 is None else round(row.sma200, 2),
                    "above50": row.above50,
                    "above200": row.above200,
                    "entry_ok": row.entry_ok,
                }
                
                # --- Added indicator fields ---
                d.update({
                    "delta_sma50_pct": (round(row.delta_sma50_pct, 2) if isinstance(row.delta_sma50_pct, (int, float)) else row.delta_sma50_pct),
                    "delta_sma200_pct": (round(row.delta_sma200_pct, 2) if isinstance(row.delta_sma200_pct, (int, float)) else row.delta_sma200_pct),
                    "rsi14": row.rsi14,
                    "rsi_zone": row.rsi_zone,
                    "macd": (round(row.macd, 4) if isinstance(row.macd, (int, float)) else row.macd),
                    "macd_signal": (round(row.macd_signal, 4) if isinstance(row.macd_signal, (int, float)) else row.macd_signal),
                    "macd_hist": (round(row.macd_hist, 4) if isinstance(row.macd_hist, (int, float)) else row.macd_hist),
                    "w52_high": (round(row.w52_high, 2) if isinstance(row.w52_high, (int, float)) else row.w52_high),
                    "w52_low": (round(row.w52_low, 2) if isinstance(row.w52_low, (int, float)) else row.w52_low),
                    "pct_to_52w_high": (round(row.pct_to_52w_high, 2) if isinstance(row.pct_to_52w_high, (int, float)) else row.pct_to_52w_high),
                    "pct_from_52w_low": (round(row.pct_from_52w_low, 2) if isinstance(row.pct_from_52w_low, (int, float)) else row.pct_from_52w_low),
                    "pivot": (round(row.pivot, 2) if isinstance(row.pivot, (int, float)) else row.pivot),
                    "vol_avg20_ratio": (round(row.vol_avg20_ratio, 2) if isinstance(row.vol_avg20_ratio, (int, float)) else row.vol_avg20_ratio),
                    "reentry": row.reentry,
                })
                if include_analyst:
                    # Merge analyst data
                    analyst_data = self._analyst_maybe(sym)
                    d.update(analyst_data)
                    # Next earnings date
                    try:
                        ne = self._analyst.next_earnings(sym)
                    except Exception:
                        ne = None
                    # If provider returns None, use Yahoo fallback (best effort)
                    if ne is None:
                        ne = _yahoo_next_earnings_fallback(sym)
                    # If still past for any reason, null it out so the UI doesn’t show stale dates.
                    if ne:
                        try:
                            if ne < _date.today().isoformat():
                                ne = None
                        except Exception:
                            pass
                    d["next_earnings"] = ne
                    # Compute distance to target percentage if both price and target are available
                    dist_pct: Optional[float] = None
                    try:
                        if d.get("avg_target") is not None and d.get("close") is not None:
                            at = float(d["avg_target"])
                            cp = float(d["close"])
                            if cp != 0:
                                dist_pct = round((at / cp - 1.0) * 100.0, 2)
                    except Exception:
                        dist_pct = None
                    d["dist_to_target_pct"] = dist_pct

                # Always include fundamental metrics when available
                try:
                    fund = self._fundamentals(sym)
                except Exception:
                    fund = {
                        "revenue_growth_pct": None,
                        "profit_margin_pct": None,
                        "market_cap": None,
                        "revenue": None,
                    }
                d.update(fund)
                out.append(d)
        return out

    # ----- Fundamentals -----
    def _fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Return basic fundamental metrics for a symbol.

        This helper attempts to load key financial metrics using the optional
        ``yfinance`` dependency. When available it retrieves values such as
        revenue growth, profit margin, market capitalisation and total
        revenue from the ticker's information. Each numeric value is
        converted into a human-friendly form (e.g. percentages are scaled
        to 100). If ``yfinance`` is not installed or the fields are not
        present, ``None`` values are returned. The returned dictionary
        contains the keys:

        ``revenue_growth_pct`` – Revenue growth percentage (e.g. 15.2)
        ``profit_margin_pct`` – Profit margin percentage (e.g. 23.5)
        ``market_cap`` – Market capitalisation (raw number)
        ``revenue`` – Total revenue (raw number)
        """
        # Use the module-level _yf imported at top if available
        if _yf is None:
            return {
                "revenue_growth_pct": None,
                "profit_margin_pct": None,
                "market_cap": None,
                "revenue": None,
            }
        try:
            t = _yf.Ticker(symbol)
            info = {}
            # Some versions of yfinance lazily fetch info; wrap in try
            try:
                info = t.get_info() or {}
            except Exception:
                info = getattr(t, "fast_info", {}) or {}
            rev_growth = info.get("revenueGrowth")
            profit_marg = info.get("profitMargins")
            market_cap = info.get("marketCap")
            revenue = info.get("totalRevenue") or info.get("revenue")
            # Convert percentages
            def to_pct(x: Any) -> Optional[float]:
                try:
                    return None if x is None else round(float(x) * 100.0, 2)
                except Exception:
                    return None
            return {
                "revenue_growth_pct": to_pct(rev_growth),
                "profit_margin_pct": to_pct(profit_marg),
                "market_cap": None if market_cap is None else float(market_cap),
                "revenue": None if revenue is None else float(revenue),
            }
        except Exception:
            return {
                "revenue_growth_pct": None,
                "profit_margin_pct": None,
                "market_cap": None,
                "revenue": None,
            }

    # ----- Breadth -----
    def risk_on(self) -> bool:
        if self._breadth_cache is not None:
            return self._breadth_cache
        total = 0
        above = 0
        for bucket, syms in self._buckets.items():
            for sym in syms:
                df = self._hist(sym)
                if df is None or df.empty:
                    continue
                if len(df) < 200:
                    continue
                close = float(df["Close"].iloc[-1])
                sma200 = self._sma(df["Close"], 200)
                if sma200 is None:
                    continue
                total += 1
                if close > sma200:
                    above += 1
        # If no data, default to risk-off
        if total == 0:
            self._breadth_cache = False
        else:
            pct = 100 * above / total
            self._breadth_cache = pct > 60.0
        return self._breadth_cache

    # ----- Analyst information -----
    def analyst_snapshot(self, symbol: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self._analyst is None:
            return out
        rec = self._analyst.recommendation(symbol)
        if rec:
            out["recommendation"] = rec
        pt = self._analyst.price_target(symbol)
        if pt:
            out["price_target"] = pt
        try:
            ne = self._analyst.next_earnings(symbol)
            if ne:
                out["next_earnings"] = ne
        except Exception:
            pass
        return out

    # ----- Bootstrapping -----
    def bootstrap(self) -> None:
        """Populate a default set of tickers. Extend or modify as needed."""
        initial_symbols = [
            "NVDA", "ASML", "LLY", "DIS", "PATH", "MSFT", "MELI", "NU", "MU", "ACLS",
            "TCEHY", "NTES", "AMD", "SMCI", "TSM", "1211.HK", "EXAS", "ISRG", "NVO",
            "1810.HK", "NFLX", "APP", "INVA", "AEVA", "AVAV", "AUTL", "COHR", "AVGO", "VRT",
            # Include the ISIN for the World Momentum ETF, which resolves to a symbol via id_map
            "IE00BP3QZ825",
        ]
        for sym in initial_symbols:
            try:
                self.add_ticker(sym, bucket="swing")
            except Exception:
                # ignore invalid symbols for now
                pass


# Singleton instance used by the FastAPI app
STORE = DataStore()