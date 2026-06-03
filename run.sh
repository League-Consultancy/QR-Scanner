#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Error: Virtual environment (.venv) not found. Please run ./setup.sh first." >&2
    exit 1
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Run app.py
echo "Running app.py..."
python app.py
