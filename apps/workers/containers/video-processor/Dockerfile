FROM --platform=linux/amd64 python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    flask \
    yt-dlp \
    assemblyai \
    requests

WORKDIR /app
COPY server.py .
EXPOSE 8080
CMD ["python", "server.py"]
