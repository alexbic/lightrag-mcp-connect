FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml README.md /app/
COPY mcp /app/mcp

RUN pip install --no-cache-dir .

ENTRYPOINT ["lightrag-mcp-connect"]
