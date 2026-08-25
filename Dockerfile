FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY quant/ quant/
# Read at startup by quant/shared/config.py to resolve DB_TARGET. The app does
# not boot without it, so it ships in the image rather than being mounted.
COPY config/db-targets.json config/db-targets.json

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready')"

CMD ["uvicorn", "quant.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
