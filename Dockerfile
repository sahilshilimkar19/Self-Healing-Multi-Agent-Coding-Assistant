FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build deps for any wheels that need compiling.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install ".[server,security,sqlite]"

# Run as non-root.
RUN useradd --create-home --uid 1001 app
USER app

EXPOSE 8000

# Default to the API server. Override with `docker run ... self-healing-coder run "<task>"`
CMD ["uvicorn", "self_healing_coder.server:app", "--host", "0.0.0.0", "--port", "8000"]
