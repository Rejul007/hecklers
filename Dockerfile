# -----------------------------------------------------------------------
# Dockerfile for AI Onboarding Engine
# Runs Ollama (qwen2.5:7b) + FastAPI in a single container
# First run downloads the model (~4.7 GB) — subsequent runs use cache
# -----------------------------------------------------------------------

FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py ai_engine.py database.py ./
COPY static/ ./static/

# Copy startup script
COPY start.sh .
RUN chmod +x start.sh

# Directory for SQLite database
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Health check (waits up to 5 min for model download on first run)
HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=10 \
    CMD curl -sf http://localhost:8000/api/sessions || exit 1

CMD ["./start.sh"]
