FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The host injects $PORT. Bind gunicorn to it. Two workers is plenty for a
# webhook receiver; backfill work runs on background threads inside a worker.
# --timeout 120 gives slow Slack/API calls room without killing the worker.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 2 --threads 4 --timeout 120 webhook_server:app"]
