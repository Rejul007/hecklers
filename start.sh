#!/bin/bash
# Start Ollama in the background
ollama serve &
OLLAMA_PID=$!

# Wait until Ollama is ready
echo "Waiting for Ollama to start..."
until curl -s http://localhost:11434 > /dev/null 2>&1; do
  sleep 1
done
echo "Ollama is ready."

# Pull model if not already present
if ! ollama list | grep -q "qwen2.5:7b"; then
  echo "Pulling qwen2.5:7b model..."
  ollama pull qwen2.5:7b
fi

# Start FastAPI
echo "Starting FastAPI..."
exec uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
