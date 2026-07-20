FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

WORKDIR /app

# Install dependencies first for layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY models ./models
RUN uv sync --locked --no-dev

ENV IMG2PERSON_INFERENCE_MODE=mock \
    IMG2PERSON_INFERENCE_PORT=8000

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "img2person-inference"]
