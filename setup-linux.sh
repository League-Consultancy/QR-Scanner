#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "=== Starting Setup Script ==="

# 1. Install uv if not available
if ! command -v uv &> /dev/null; then
    echo "uv is not installed. Installing uv..."
    if command -v curl &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget &> /dev/null; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        echo "Error: curl or wget is required to install uv." >&2
        exit 1
    fi
    
    # Add uv to PATH for the rest of this script
    export PATH="$HOME/.local/bin:$PATH"
    
    # Confirm uv installation
    if ! command -v uv &> /dev/null; then
        echo "Error: uv installation succeeded but 'uv' command is still not found in PATH." >&2
        exit 1
    fi
else
    echo "✔ uv is already installed."
fi

# Show uv version
uv --version

# 2. Install Python 3.12.13 using uv
echo "Installing Python 3.12.13 using uv..."
uv python install 3.12.13

# 3. Create virtual environment (.venv) using Python 3.12.13
echo "Creating virtual environment (.venv) using Python 3.12.13..."
uv venv .venv --python 3.12.13

# 4. Install all requirements
if [ -f requirements.txt ]; then
    echo "Installing requirements from requirements.txt..."
    uv pip install --python .venv -r requirements.txt
    echo "✔ Requirements installed successfully."
else
    echo "⚠ requirements.txt not found! Skipping packages installation."
fi

echo "=== Setup Completed Successfully ==="
echo "To Run the Software, run: ./run-linux.sh"