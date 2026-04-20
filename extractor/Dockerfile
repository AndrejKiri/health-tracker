# For native macOS development with Metal GPU acceleration, use: make watch / make extract
# See README. This Dockerfile is for optional full-Docker deployment only.
FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    # Create a non-root user; UID 1001 avoids collision with the default
    # host user (UID 1000) while remaining predictable.
    && useradd -r -u 1001 -U -d /app extractor \
    && mkdir -p /app /data/inbox /data/processed /data/failed \
    && chown -R extractor:extractor /app /data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=extractor:extractor . /app/extractor/

ENV PYTHONPATH=/app

USER extractor

# Default: run the watcher. Override with docker compose command for other modes.
CMD ["python", "-m", "extractor.cli", "watch"]
