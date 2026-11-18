FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY league_hub ./league_hub
COPY wsgi.py .
ENV APP_ENV=production PORT=8000
# One worker process keeps SQLite safe and is plenty for ~20 users; threads handle concurrency.
CMD ["sh", "-c", "gunicorn wsgi:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4"]
