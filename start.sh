#!/bin/bash
set -e

# ── .env check ────────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found."
  echo "Copy .env.example to .env and fill in your credentials:"
  echo "  cp .env.example .env"
  exit 1
fi

# ── Python virtualenv + dependencies ──────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
fi

echo "Installing Python dependencies..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

# ── Ollama ────────────────────────────────────────────────────────────────────
if ! command -v ollama &> /dev/null; then
  echo "Ollama not found. Installing..."
  curl -fsSL https://ollama.com/install.sh | sh
  echo "Ollama installed."
fi

# Start Ollama in the background
ollama serve &
OLLAMA_PID=$!

echo "Waiting for Ollama to start..."
until curl -s http://localhost:11434 > /dev/null 2>&1; do
  sleep 1
done
echo "Ollama is ready."

if ! ollama list | grep -q "qwen2.5:7b"; then
  echo "Pulling qwen2.5:7b model..."
  ollama pull qwen2.5:7b
fi

# ── FastAPI ───────────────────────────────────────────────────────────────────
echo "Starting FastAPI..."
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
