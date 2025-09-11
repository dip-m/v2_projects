# VoyagerVista Investing Dashboard (Render-ready)
FROM python:3.12-slim
WORKDIR /app
COPY dashboard_app /app/dashboard_app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
ENV PYTHONUNBUFFERED=1
CMD ["sh","-c","uvicorn dashboard_app.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
