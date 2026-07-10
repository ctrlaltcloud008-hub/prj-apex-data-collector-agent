FROM python:3.14-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
	build-essential \
	&& rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "uv>=0.11.12"

COPY pyproject.toml uv.lock README.md ./

RUN uv venv /opt/venv && \
	uv pip install --no-cache-dir --python /opt/venv/bin/python -r pyproject.toml

COPY src/ src/
RUN uv pip install --no-cache-dir --python /opt/venv/bin/python --no-deps .

FROM python:3.14-slim

LABEL maintainer="Amith Sai"

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PATH="/opt/venv/bin:$PATH" \
	ENV=production

COPY --from=builder /opt/venv /opt/venv

RUN adduser --disabled-password --gecos "" --no-create-home --uid 10001 appuser
USER 10001
WORKDIR /app

EXPOSE 8080

# The read-only MCPs (logging, spanner, pubsub) are deployed as sidecar
# containers in the same Cloud Run service and reached over localhost; their
# URLs are supplied via LOGGING_MCP_URL / SPANNER_MCP_URL / PUBSUB_MCP_URL. An
# unhealthy sidecar surfaces as source_unavailable per request, not a crash.
CMD ["data-collector"]
