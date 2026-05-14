FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Installer les dépendances en cache-layer séparé
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copier le code source et installer le projet
COPY . .
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "python", "main.py"]
