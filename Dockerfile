FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY style.md ./
RUN uv sync --frozen --no-dev
CMD ["uv", "run", "--no-sync", "antoncopilot"]
