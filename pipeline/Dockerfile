# OpenPali pipeline/platform image: API, Prefect worker, MLflow server, and
# job services all run from this one image (modular monolith).
FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Non-root runtime user (release requirement).
RUN groupadd --gid 10001 openpali && \
    useradd --uid 10001 --gid 10001 --create-home openpali

WORKDIR /app

# Locked third-party dependencies first (cacheable layer).
COPY requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt

# Project code.
COPY pyproject.toml alembic.ini README.md ./
COPY openpali ./openpali
COPY palisades ./palisades
COPY core ./core
COPY migrations ./migrations
COPY tests ./tests
RUN pip install --no-cache-dir --no-deps -e .

USER openpali
