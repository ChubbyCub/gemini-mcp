FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy source
COPY src/ src/

# Create mount point for file-based input
RUN mkdir -p /data

# MCP servers communicate over stdio — no port needed
CMD ["python", "src/server.py"]
