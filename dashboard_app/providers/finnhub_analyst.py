from __future__ import annotations
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, date
import requests

try:
    import yfinance as yf  # optional but recommended
except Exception:
    yf = None

FINNHUB_URL = "https://api.finnhub.io/api/v1"

def _env_finnhub_key() -> Optional[str]:
    return os.getenv("FINNHUB_API_KEY") or os.getenv("FINNHUB_TOKEN")
    
    
def _first_future_iso(cands: list[str]) -> Optional[str]:
    """Return earliest date >= today in ISO (YYYY-MM-DD); None if nothing future."""
    if not cands:
        return None
    today = date.today().isoformat()
    future = sorted([d for d in cands if d >= today])
    return future[0] if future else None

def _finnhub_next_earnings(symbol: str, token: Optional[str]) -> Optional[str]:
    """Query Finnhub earnings calendar for next 365 days; return earliest future date."""
    if not token:
        return None
    try:
        start = date.today().isoformat()
        end   = (date.today() + timedelta(days=365)).isoformat()
        # Finnhub supports either symbol filter or full calendar; use symbol to reduce payload.
        url = f"{FINNHUB_URL}/calendar/earnings"
        params = {"symbol": symbol.upper(), "from": start, "to": end, "token": token}
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return None
        j = r.json() or {}
        rows = j.get("earningsCalendar") or []
        # Rows can contain date under 'date' or 'epsReportDate' depending on version
        cands: list[str] = []
        for row in rows:
            d = (row.get("date") or row.get("epsReportDate") or "").split("T")[0]
            if len(d) == 10:
                cands.append(d)
        return _first_future_iso(cands)
    except Exception:
        return None


def _latest_reco_from_finnhub(symbol: str, token: str) -> Optional[Dict[str, Any]]:
    url = f"{FINNHUB_URL}/stock/recommendation"
    r = requests.get(url, params={"symbol": symbol, "token": token}, timeout=15)
    if r.status_code != 200:
        return None
    data = r.json()
    if not isinstance(data, list) or not data:
        return None
    # Most recent by period (YYYY-MM)
    latest = sorted(data, key=lambda x: str(x.get("period") or ""), reverse=True)[0]
    counts = {
        "strongBuy": int(latest.get("strongBuy") or 0),
        "buy":       int(latest.get("buy") or 0),
        "hold":      int(latest.get("hold") or 0),
        "sell":      int(latest.get("sell") or 0),
        "strongSell":int(latest.get("strongSell") or 0),
    }
    total = sum(counts.values())
    if total <= 0:
        total = None
        percent = {}
    else:
        percent = {
            "buy": 100.0 * (counts["strongBuy"] + counts["buy"]) / total,
            "hold":100.0 * counts["hold"] / total,
            "sell":100.0 * (counts["sell"] + counts["strongSell"]) / total,
        }
    return {
        "as_of": latest.get("period") or None,
        "counts": counts,
        "percent": percent if percent else None,
        "total": total,
    }

def _yahoo_price_target(symbol: str) -> Optional[Dict[str, Any]]:
    if yf is None:
        return None
    try:
        t = yf.Ticker(symbol)
        info = {}
        try:
            info = t.get_info()
        except Exception:
            pass
        if not info:
            info = getattr(t, "fast_info", {}) or {}

        def pick(keys: List[str]):
            for k in keys:
                v = info.get(k)
                if v is not None:
                    return float(v)
            return None

        out = {
            "avg_target": pick(["targetMeanPrice", "targetMean"]),
            "median":     pick(["targetMedianPrice", "targetMedian"]),
            "high":       pick(["targetHighPrice", "targetHigh"]),
            "low":        pick(["targetLowPrice", "targetLow"]),
            "as_of": None,
        }
        if out["avg_target"] is None and out["high"] is not None and out["low"] is not None:
            out["avg_target"] = (out["high"] + out["low"]) / 2.0
        if all(out[k] is None for k in ("avg_target", "median", "high", "low")):
            return None
        return out
    except Exception:
        return None

def _yahoo_next_earnings(symbol: str) -> Optional[str]:
    if yf is None:
        return None
    try:
        t = yf.Ticker(symbol)
        cands: List[datetime] = []

        # get_calendar / calendar
        cal_fn = getattr(t, "get_calendar", None)
        cdf = cal_fn() if callable(cal_fn) else getattr(t, "calendar", None)
        def _to_date(v):
            try:
                if hasattr(v, "to_pydatetime"):
                    return v.to_pydatetime().date().isoformat()
                if isinstance(v, (int, float)):
                    return datetime.utcfromtimestamp(float(v)).date().isoformat()
                if isinstance(v, str):
                    return datetime.fromisoformat(v.split()[0]).date().isoformat()
            except Exception:
                return None
            return None
        if cdf is not None and hasattr(cdf, "index"):
            for key in ["Earnings Date", "EarningsDate", "Earnings Date Start", "Earnings Date End"]:
                if key in cdf.index:
                    val = cdf.loc[key]
                    vals = getattr(val, "values", [val])
                    for v in (vals if isinstance(vals, (list, tuple)) else [vals]):
                        d = _to_date(v)
                        if d: cands.append(d)

        if not cands:
            try:
                ed = t.get_earnings_dates(limit=40)
                if ed is not None and not ed.empty:
                    for ts in ed.index:
                        d = _to_date(ts)
                        if d: cands.append(d)
            except Exception:
                pass

        if not cands:
            return None
        today = datetime.utcnow().date().isoformat()
        fut = sorted([d for d in cands if d >= today])
        return fut[0] if fut else sorted(cands)[-1]
    except Exception:
        return None

class FinnhubAnalystProvider:
    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or _env_finnhub_key()

    def recommendation(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.token:
            return None
        sym = (symbol or "").upper()
        return _latest_reco_from_finnhub(sym, self.token)

    def next_earnings(self, symbol: str) -> Optional[str]:
        # 1) Finnhub future-first
        sym = (symbol or "").upper()
        d = _finnhub_next_earnings(sym, self.token)
        if d:
            return d
        # 2) Yahoo fallback (your existing helper)
        return _yahoo_next_earnings(sym)


    def price_target(self, symbol: str) -> Optional[Dict[str, Any]]:
        sym = (symbol or "").upper()
        return _yahoo_price_target(sym)
