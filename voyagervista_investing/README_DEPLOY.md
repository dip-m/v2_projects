# VoyagerVista — Investing Dashboard

## Quick Start (Docker)
```bash
docker build -t voyagervista-dashboard .
docker run -p 8000:8000 -v $(pwd)/dashboard_app/data:/app/dashboard_app/data voyagervista-dashboard
# Open http://localhost:8000
```

## Persisted Data
- **buckets.json** — your bucket definitions
- **tickers.json** — your tickers (with metadata)
The app still writes a legacy `state.json` for backward compatibility.

## Env & Requirements
Python 3.12+. Install dependencies:
```bash
pip install -r requirements.txt
```
Run locally:
```bash
uvicorn dashboard_app.app:app --host 0.0.0.0 --port 8000
```

## Branding
- Logo: `dashboard_app/static/img/voyagervista_logo.png`
- Favicon: `dashboard_app/static/favicon.ico`
