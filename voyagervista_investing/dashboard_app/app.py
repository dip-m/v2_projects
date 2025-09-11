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


app = FastAPI(title="Investment Dashboard", version="2.0")

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