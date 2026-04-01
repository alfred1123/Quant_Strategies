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
    echo "NOTE: No scripts/.env file found."
    echo "Create one with your API keys:"
    echo ""
    echo "  cat > scripts/.env << 'EOF'"
    echo "  GLASSNODE_API_KEY=your_key_here"
    echo "  FUTU_HOST=127.0.0.1"
    echo "  FUTU_PORT=11111"
    echo "  BYBIT_API_KEY=your_key_here"
    echo "  BYBIT_SECRET_KEY=your_key_here"
    echo "  EOF"
    echo ""
else
    echo "scripts/.env found."
fi

echo ""
echo "Setup complete! Activate your environment with:"
echo "  source env/bin/activate"
echo ""
echo "Run a backtest with:"
echo "  cd scripts/backtest && python main.py"
