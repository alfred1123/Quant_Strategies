# Getting Started

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Tested on 3.12.3 |
| Node.js 24+ | Managed via nvm — `setup.sh` installs automatically from `.nvmrc` |
| pip | Used by `setup.sh` to install Python dependencies |
| Git | To clone the repo |
| Linux / macOS | Windows works but `setup.sh` is a bash script — run manually or use WSL |
| PostgreSQL 17 | Connected via `localhost:5433` (AWS SSM port-forward) — required for REFDATA dropdowns |

## Setup

### Option A: Automated (recommended)

```bash
git clone https://github.com/alfred1123/Quant_Strategies.git
cd Quant_Strategies
./setup.sh
```

This script:

1. Creates a Python virtual environment at `env/`
2. Upgrades pip and installs all packages from `requirements.txt`
3. Checks that `.env` exists (exits with error if missing)
4. Installs nvm (if not present) and the Node.js version pinned in `.nvmrc`
5. Runs `npm install` in `frontend/`

### Option B: Manual

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit with your keys
```

## Running

```bash
# Terminal 1 — FastAPI backend
source env/bin/activate
uvicorn api.main:app --reload

# Terminal 2 — React frontend
cd frontend && npm run dev
```

Open `http://localhost:5173`. The UI lets you configure symbol, dates, indicator, strategy, parameters, and run grid-search optimization or single backtests — all from a collapsible side drawer. Dropdowns are populated live from the REFDATA database.

## Serving the Wiki Locally

```bash
source env/bin/activate
mkdocs serve
```

Open `http://localhost:8001` to browse the wiki.
