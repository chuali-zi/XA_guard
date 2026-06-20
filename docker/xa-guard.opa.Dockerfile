# OPA-enabled XA-Guard image. The OPA executable comes from the official image.
ARG OPA_IMAGE=openpolicyagent/opa:1.4.2-static
FROM ${OPA_IMAGE} AS opa

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src:/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY --from=opa /opa /usr/local/bin/opa
RUN test -x /usr/local/bin/opa

COPY pyproject.toml README.md ./
COPY bench ./bench
COPY configs ./configs
COPY demo ./demo
COPY policies ./policies
COPY scripts ./scripts
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install -e ".[bench,policy,aibom,http]" \
    && mkdir -p /app/logs/audit /app/logs/runtime

EXPOSE 3000
CMD ["python", "-m", "xa_guard.server", "--config", "configs/xa-guard.opa.yaml"]
