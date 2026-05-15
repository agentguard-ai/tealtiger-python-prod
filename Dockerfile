# TealTiger Python SDK - Production Image
# Multi-stage build for minimal image size

# Stage 1: Builder
FROM python:3.11-slim as builder

LABEL maintainer="TealTiger Team <support@tealtiger.co.in>"
LABEL description="TealTiger Python SDK - AI agent security with guardrails and cost tracking"

WORKDIR /build

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

# Build wheel
RUN pip install --no-cache-dir build && \
    python -m build --wheel

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy wheel from builder and install
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && \
    rm -rf /tmp/*.whl /root/.cache

# Copy examples and documentation
COPY examples/ /app/examples/
COPY README.md LICENSE /app/

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash tealtiger && \
    chown -R tealtiger:tealtiger /app

USER tealtiger

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default command
CMD ["python"]
