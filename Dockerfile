FROM python:3.13-slim

ARG FORCE_READINESS_FAILURE=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FORCE_READINESS_FAILURE=${FORCE_READINESS_FAILURE}

WORKDIR /app

RUN addgroup --system northstar && adduser --system --ingroup northstar northstar

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY --chown=northstar:northstar app ./app
COPY --chown=northstar:northstar src ./src
COPY --chown=northstar:northstar data ./data
COPY --chown=northstar:northstar scripts ./scripts

RUN mkdir -p /app/outputs && chown -R northstar:northstar /app/data /app/outputs
USER northstar

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=8s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
