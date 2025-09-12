# VoyagerVista Investing Dashboard (Render-ready)
FROM python:3.12-slim

# Needed for HTTPS and time/date (prevents yfinance flakiness)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates && rm -rf /var/lib/apt/lists/*
ENV TZ=UTC PYTHONUNBUFFERED=1

WORKDIR /app
COPY dashboard_app /app/dashboard_app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Render sets $PORT dynamically
CMD ["sh","-c","uvicorn dashboard_app.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
