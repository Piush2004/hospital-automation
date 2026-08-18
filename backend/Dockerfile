FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Migrations run at container start so `docker compose up` is one command,
# not "up, then exec in and migrate." --ws-max-size is raised because the
# voice channel's WAV replies can exceed uvicorn's 1MB default websocket
# frame size (found via testing, see CLAUDE.md).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --ws-max-size 20971520"]
