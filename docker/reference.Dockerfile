FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY bench ./bench
RUN python -m pip install --no-cache-dir ".[reference]" \
    && useradd --create-home --uid 10001 xa-guard \
    && mkdir -p /app/logs/reference-audit \
    && chown -R xa-guard:xa-guard /app/logs

COPY configs ./configs
COPY policies ./policies

USER 10001:10001
CMD ["python", "-m", "xa_guard.control.api"]

