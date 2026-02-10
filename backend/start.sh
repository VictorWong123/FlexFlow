#!/bin/bash
# Start both the FastAPI health server and the agent worker

# Start FastAPI in the background for healthchecks
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} &

# Start the agent worker in the foreground
python -m app.agent start
