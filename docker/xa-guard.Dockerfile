# XA-Guard service image for L3 one-command deployment.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src:/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY bench ./bench
COPY configs ./configs
COPY demo ./demo
COPY policies ./policies
COPY scripts ./scripts
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install -e ".[bench,policy,aibom,http]"

RUN mkdir -p /app/logs/audit /app/logs/runtime

EXPOSE 3000

CMD ["python", "-m", "xa_guard.server", "--config", "configs/xa-guard.docker.yaml"]
