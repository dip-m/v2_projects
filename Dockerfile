# VoyagerVista Investing Dashboard (Render-ready)
FROM python:3.12-slim

# Install tzdata and CA certs for outbound HTTPS & timezones
RUN apt-get update &&     apt-get install -y --no-install-recommends tzdata ca-certificates &&     rm -rf /var/lib/apt/lists/*

ENV TZ=UTC
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY dashboard_app /app/dashboard_app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Render provides $PORT; default to 8000 for local
CMD ["sh","-c","uvicorn dashboard_app.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
