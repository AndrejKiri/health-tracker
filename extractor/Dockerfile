FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/extractor/

ENV PYTHONPATH=/app

# Default: run the watcher. Override with docker compose command for other modes.
CMD ["python", "-m", "extractor.cli", "watch"]
