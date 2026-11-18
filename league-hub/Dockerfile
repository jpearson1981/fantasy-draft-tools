FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY league_hub ./league_hub
COPY wsgi.py .
ENV APP_ENV=production DATABASE_PATH=/data/league_hub.db PORT=8000
# SQLite allows one writer: one worker process, several threads.
CMD ["sh", "-c", "gunicorn wsgi:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4"]
