#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$REPO_DIR/env"

echo "=== Quant Strategies Setup ==="

# 1. Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR/bin" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# 2. Activate
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# 3. Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip --quiet

# 4. Install dependencies
echo "Installing dependencies..."
pip install -r "$REPO_DIR/requirements.txt" --quiet

# 5. Check for .env configuration
if [ ! -f "$REPO_DIR/scripts/.env" ]; then
    echo ""
    echo "ERROR: No scripts/.env file found."
    echo "Copy the template and fill in your API keys:"
    echo ""
    echo "  cp scripts/.env.example scripts/.env"
    echo "  # then edit scripts/.env with your keys"
    echo ""
    exit 1
else
    echo "scripts/.env found."
fi

echo ""
echo "Setup complete! Activate your environment with:"
echo "  source env/bin/activate"
echo ""
echo "Run a backtest with:"
echo "  cd scripts/bt && python main.py"
echo ""
echo "Or launch the dashboard:"
echo "  cd scripts/bt && streamlit run app.py"
