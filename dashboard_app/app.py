"""FastAPI entry point for the investment dashboard.

This module exposes a set of REST endpoints for managing tickers and
buckets, retrieving technical signals, computing market breadth and
obtaining analyst snapshots. The routes defined here interact with a
singleton ``STORE`` provided by ``data_store.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
os.environ["FINNHUB_API_KEY"] = "d3186phr01qr52j65ergd3186phr01qr52j65es0"
from .data_store import STORE


app = FastAPI(title="Investment Dashboard", version="2.1")
@app.get("/healthz")
def healthz():
    return {"ok": True, "app": app.title, "version": app.version}

@app.get("/routes")
def list_routes():
    paths = []
    try:
        for r in app.router.routes:
            if hasattr(r, "methods") and hasattr(r, "path"):
                paths.append({"path": r.path, "methods": sorted(list(r.methods))})
    except Exception:
        pass
    return {"routes": sorted(paths, key=lambda x: x["path"])}


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


class AddTickerBody(BaseModel):
    symbol: str
    bucket: Optional[str] = None
    type: Optional[str] = None  # equity or etf


class MoveBody(BaseModel):
    symbol: str
    bucket: str


class BucketBody(BaseModel):
    name: str


class RenameBucketBody(BaseModel):
    old: str
    new: str


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/buckets")
def get_buckets() -> Dict[str, Any]:
    return {"buckets": STORE._buckets}


@app.post("/buckets")
def create_bucket(body: BucketBody) -> Dict[str, Any]:
    if not body.name:
        raise HTTPException(400, "Bucket name is required")
    STORE.create_bucket(body.name)
    return {"ok": True}


@app.patch("/buckets/rename")
def rename_bucket(body: RenameBucketBody) -> Dict[str, Any]:
    try:
        STORE.rename_bucket(body.old, body.new)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.delete("/buckets/{name}")
def delete_bucket(name: str) -> Dict[str, Any]:
    STORE.delete_bucket(name)
    return {"ok": True}


@app.get("/tickers")
def list_tickers() -> Dict[str, Any]:
    return {"tickers": list(STORE._tickers.keys())}


@app.post("/tickers")
def add_ticker(body: AddTickerBody) -> Dict[str, Any]:
    try:
        STORE.add_ticker(body.symbol, bucket=body.bucket, type_hint=body.type)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/tickers/{symbol}")
def delete_ticker(symbol: str) -> Dict[str, Any]:
    STORE.remove_ticker(symbol)
    return {"ok": True}


@app.post("/tickers/move")
def move_ticker(body: MoveBody) -> Dict[str, Any]:
    STORE.move_ticker(body.symbol, body.bucket)
    return {"ok": True}


@app.get("/indicators")
def indicators(symbol: Optional[str] = None):
    """Return technical indicators for all symbols or a single symbol."""
    rows = STORE.signals(include_analyst=False)
    out = []
    for d in rows:
        if symbol and d.get('symbol') != symbol:
            continue
        out.append({
            'symbol': d.get('symbol'),
            'delta_sma50_pct': d.get('delta_sma50_pct'),
            'delta_sma200_pct': d.get('delta_sma200_pct'),
            'rsi14': d.get('rsi14'),
            'rsi_zone': d.get('rsi_zone'),
            'macd': d.get('macd'),
            'macd_signal': d.get('macd_signal'),
            'macd_hist': d.get('macd_hist'),
            'w52_high': d.get('w52_high'),
            'w52_low': d.get('w52_low'),
            'pct_to_52w_high': d.get('pct_to_52w_high'),
            'pct_from_52w_low': d.get('pct_from_52w_low'),
            'pivot': d.get('pivot'),
            'vol_avg20_ratio': d.get('vol_avg20_ratio'),
            'reentry': d.get('reentry'),
        })
    return {'indicators': out}


@app.get("/debug/yahoo")
def yahoo_debug(symbol: str, period: str = "6mo", interval: str = "1d"):
    """
    Fetch raw OHLCV from Yahoo Finance directly (via yfinance) to troubleshoot data availability.
    Returns the last 40 rows and basic stats.
    """
    try:
        from .providers.yahoo_prices import YahooPriceProvider
        import math
        yp = YahooPriceProvider()
        df = yp.recent_ohlc(symbol, period=period, interval=interval)
        if df is None:
            return {"symbol": symbol, "note": "yfinance returned None (fetch failed)"}
        if df.empty:
            return {"symbol": symbol, "note": "yfinance returned empty DataFrame", "rows": 0}
        tail = df.tail(40).reset_index()
        # Convert Timestamp to ISO
        tail["Date"] = tail["Date"].astype(str)
        # Compute quick indicators inline for validation
        close = df["Close"]
        import pandas as pd
        def sma(s, w):
            try:
                return float(s.tail(w).mean())
            except Exception:
                return None
        # RSI
        def rsi(series, period=14):
            try:
                delta = series.diff()
                gains = delta.clip(lower=0).rolling(window=period).mean()
                losses = (-delta.clip(upper=0)).rolling(window=period).mean()
                rs = gains / (losses.replace(0, 1e-9))
                r = 100 - (100 / (1 + rs))
                val = float(r.iloc[-1])
                return round(val, 2)
            except Exception:
                return None
        # MACD
        def macd(series, fast=12, slow=26, signal=9):
            try:
                ema_fast = series.ewm(span=fast, adjust=False).mean()
                ema_slow = series.ewm(span=slow, adjust=False).mean()
                m = ema_fast - ema_slow
                ms = m.ewm(span=signal, adjust=False).mean()
                mh = m - ms
                return float(m.iloc[-1]), float(ms.iloc[-1]), float(mh.iloc[-1])
            except Exception:
                return None, None, None
        sma50 = sma(close, 50)
        sma200 = sma(close, 200)
        r = rsi(close, 14)
        m, ms, mh = macd(close)
        # 52w
        window = min(len(df), 252)
        w52h = float(df["High"].tail(window).max()) if window > 0 else None
        w52l = float(df["Low"].tail(window).min()) if window > 0 else None
        pivot = None
        if len(df) >= 2:
            prev = df.iloc[-2]
            pivot = round((float(prev["High"]) + float(prev["Low"]) + float(prev["Close"])) / 3.0, 2)
        payload = {
            "symbol": symbol,
            "rows": int(len(df)),
            "last_close": float(close.iloc[-1]) if len(close) else None,
            "sma50": sma50,
            "sma200": sma200,
            "rsi14": r,
            "macd": m, "macd_signal": ms, "macd_hist": mh,
            "w52_high": w52h, "w52_low": w52l,
            "pivot": pivot,
            "tail": tail.to_dict(orient="records"),
        }
        return payload
    except Exception as ex:
        return {"symbol": symbol, "error": str(ex)}

@app.get("/debug/indicators")
def indicators_debug(symbol: str):
    """
    Returns the indicators for a single symbol as computed by DataStore._calc_signal,
    to confirm server-side calculation path.
    """
    try:
        d = STORE.signals(include_analyst=False)
        for row in d:
            if row.get("symbol") == symbol:
                return row
        return {"note": "symbol not found in current buckets; add it to a bucket first"}
    except Exception as ex:
        return {"error": str(ex)}

@app.get("/signals")
def signals(include_analyst: bool = True) -> Dict[str, Any]:
    """Return all signal dictionaries. Query param include_analyst controls analyst data."""
    rows = STORE.signals(include_analyst=include_analyst)
    return {"signals": rows}

@app.post("/save")
def save_state() -> Dict[str, Any]:
    """Persist current tickers and buckets to disk."""
    # Persistence occurs automatically when modifying state; this endpoint triggers manual save
    try:
        # call internal save method
        STORE._save_state()
        return {"ok": True}
    except Exception:
        raise HTTPException(500, "Failed to save state")


@app.get("/breadth")
def breadth() -> Dict[str, Any]:
    return {"risk_on": STORE.risk_on()}


@app.get("/analyst/{symbol}")
def analyst(symbol: str) -> Dict[str, Any]:
    data = STORE.analyst_snapshot(symbol)
    if not data:
        return {"note": "Analyst data unavailable"}
    return data