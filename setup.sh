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
if [ ! -f "$REPO_DIR/.env" ]; then
    echo ""
    echo "ERROR: No .env file found."
    echo "Copy the template and fill in your API keys:"
    echo ""
    echo "  cp .env.example .env"
    echo "  # then edit .env with your keys"
    echo ""
    exit 1
else
    echo ".env found."
fi

# 6. Node.js via nvm
echo ""
echo "=== Node.js Setup ==="
export NVM_DIR="$HOME/.nvm"
if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    echo "Installing nvm..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash
    # shellcheck source=/dev/null
    source "$NVM_DIR/nvm.sh"
else
    # shellcheck source=/dev/null
    source "$NVM_DIR/nvm.sh"
    echo "nvm already installed."
fi

echo "Installing Node.js (version from .nvmrc)..."
nvm install
nvm use

# 7. Frontend dependencies
echo ""
echo "=== Frontend Setup ==="
FRONTEND_DIR="$REPO_DIR/frontend"
if [ -d "$FRONTEND_DIR" ]; then
    echo "Installing frontend dependencies..."
    cd "$FRONTEND_DIR" && npm install --silent
    cd "$REPO_DIR"
    echo "Frontend dependencies installed."
else
    echo "WARNING: frontend/ directory not found — skipping npm install."
fi

echo ""
echo "Setup complete!"
echo ""
echo "Start the backend:"
echo "  source env/bin/activate && uvicorn api.main:app --reload"
echo ""
echo "Start the frontend (in a separate terminal):"
echo "  cd frontend && npm run dev"
echo ""
echo "Run a backtest:"
echo "  source env/bin/activate && cd src && python main.py"
