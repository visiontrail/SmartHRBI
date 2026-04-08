FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt

RUN mkdir -p /app/apps /app/data/uploads
COPY apps/__init__.py /app/apps/__init__.py
COPY apps/api /app/apps/api
COPY models /app/models

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=6 CMD curl -fsS http://127.0.0.1:8000/healthz >/dev/null || exit 1

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
