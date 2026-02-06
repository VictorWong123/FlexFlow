#!/bin/bash
# FlexFlow backend setup - requires Python 3.10+

set -e

# Find Python 3.10+
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
  if command -v $cmd &>/dev/null; then
    VER=$($cmd -c 'import sys; print(sys.version_info.major, sys.version_info.minor)' 2>/dev/null || true)
    if [ -n "$VER" ]; then
      MAJOR=$(echo $VER | cut -d' ' -f1)
      MINOR=$(echo $VER | cut -d' ' -f2)
      if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 10 ]; then
        PYTHON=$cmd
        break
      fi
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "ERROR: Python 3.10+ is required but not found."
  echo ""
  echo "Install Python 3.10+ on macOS:"
  echo "  brew install python@3.11"
  echo ""
  echo "Or download from: https://www.python.org/downloads/"
  exit 1
fi

echo "Using: $($PYTHON --version)"

# Create venv
echo "Creating virtual environment..."
$PYTHON -m venv .venv

# Activate and install
echo "Installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Setup complete! Run:"
echo "  source .venv/bin/activate"
echo "  uvicorn main:app --reload --port 8000"
echo ""
echo "For the agent (in another terminal):"
echo "  cd backend && source .venv/bin/activate && python -m app.agent dev"
