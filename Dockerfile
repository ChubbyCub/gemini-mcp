FROM python:3.12-slim

WORKDIR /app

# poppler is required by zerox for PDF-to-image conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy source
COPY src/ src/

# MCP servers communicate over stdio — no port needed
CMD ["python", "src/server.py"]
