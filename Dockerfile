FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
COPY finops ./finops
COPY alembic.ini ./

RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src

ENTRYPOINT ["python", "-m", "reflight.cli"]
CMD ["api"]
