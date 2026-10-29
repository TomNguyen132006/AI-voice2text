# Backend image (S9-1): FastAPI + ffmpeg. Build from the repo root or from backend/:
#   docker build -t lecturesque-backend backend
#   docker run -p 8000:8000 --env-file .env lecturesque-backend
# No torch / NeMo here (requirements.txt is the deploy list): this image takes transcripts (.txt/.srt/.vtt).
# Audio needs a GPU engine, see README "Deployment" and "Parakeet local test environment".
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
# Hosts such as Render set $PORT; 8000 otherwise.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
