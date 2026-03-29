# Quant Strategies

Backtesting and live-trading framework for crypto and equity markets. Strategies are developed around technical indicators (SMA, EMA, RSI, Bollinger Z-score, Stochastic Oscillator), optimized via grid search over parameter space, and deployed to Bybit for live execution.

**Target:** strategies with Sharpe > 1.5 and strong Calmar ratios.

---

## Repository Structure

```
Quant_Strategies/
├── scripts/
│   ├── backtest/            # Backtesting pipeline
│   │   ├── data.py          # Data retrieval (Futu, Glassnode, Bybit)
│   │   ├── ta.py            # Technical analysis indicators
│   │   ├── strat.py         # Signal generation strategies
│   │   ├── perf.py          # Performance metrics & PnL engine
│   │   ├── param_opt.py     # Grid-search parameter optimization
│   │   └── main.py          # Backtest entry point — wires everything together
│   │
│   ├── bybit_trade_data.py  # Live data collector (writes to data.csv)
│   ├── bybit._trade.py      # Live trading loop (reads data.csv, places orders)
│   ├── prod_data.py         # (WIP) Real-time data class
│   └── .env                 # API keys (gitignored)
│
├── notebooks/               # Jupyter exploration & prototyping
├── data/
│   ├── raw/                 # Source datasets (Excel, zips)
│   └── processed/           # Cleaned datasets
├── results/                 # Output charts (PNGs)
├── data.csv                 # Live OHLCV feed (created at runtime)
└── Trading Strategy.html    # Plotly backtest visualization
```

---

## Script Flow

The codebase has two independent pipelines — **backtest** and **live trading** — that share the same strategy logic conceptually but are wired separately.

### Backtest Pipeline

```
data.py ──► ta.py ──► strat.py ──► perf.py ──► param_opt.py
  │            │           │           │              │
  │            │           │           │              └─ Grid search over (window, signal)
  │            │           │           │                 pairs, returns best Sharpe
  │            │           │           │
  │            │           │           └─ Computes PnL, cumulative return, drawdown,
  │            │           │              Sharpe, Calmar vs buy-and-hold benchmark
  │            │           │
  │            │           └─ Generates position array {-1, 0, 1} from indicator
  │            │              vs threshold signal
  │            │
  │            └─ Calculates indicator values (SMA, EMA, RSI, Bollinger Z,
  │               Stochastic) on the factor column
  │
  └─ Fetches historical OHLCV from Glassnode, Futu OpenD, or Bybit
```

**`main.py` orchestrates the full flow:**

1. Pull price/factor data via `Glassnode` (or `FutuOpenD`)
2. Compute indicators via `TechnicalAnalysis`
3. Generate positions via `Strategy`
4. Evaluate performance via `Performance`
5. Optimize parameters via `ParametersOptimization`
6. Visualize Sharpe heatmap with seaborn

### Live Trading Pipeline

```
bybit_trade_data.py ──writes──► data.csv ──read by──► bybit._trade.py
        │                                                    │
        │  Polls Bybit every minute,                         │  Reads data.csv every minute,
        │  appends 1m OHLCV candles                          │  computes rolling z-score,
        │  to data.csv                                       │  sends market orders to Bybit
        │                                                    │
        └── runs continuously                                └── runs continuously
```

These two scripts run as **separate processes** side by side.

---

## How to Backtest

### 1. Setup

```bash
# Create and activate virtual environment
python -m venv env
source env/bin/activate

# Install dependencies
pip install pandas numpy requests python-dotenv ccxt matplotlib plotly seaborn futu-api

# Configure API keys
cat > scripts/.env << 'EOF'
GLASSNODE_API_KEY=your_key_here
FUTU_HOST=127.0.0.1
FUTU_PORT=11111
BYBIT_API_KEY=your_key_here
BYBIT_SECRET_KEY=your_key_here
EOF
```

### 2. Run a Single Backtest

Edit `scripts/backtest/main.py` to configure your run:

```python
# Choose data source and date range
glassnode = Glassnode()
price = glassnode.get_historical_price('BTC', '2020-05-11', '2023-04-22', '10m')

# Set parameters
trading_period = 365 * 24 * 6   # number of 10m bars in a year
period = 10                      # indicator lookback window
signal = 1                       # position threshold

# Choose indicator + strategy combo
ta = TechnicalAnalysis(df)
strat = Strategy()
perf = Performance(ta.data, trading_period, ta.get_bollinger_band, strat.momentum_const_signal, period, signal)

# View results
print(perf.get_strategy_performance())
print(perf.get_buy_hold_performance())
```

Then run from the backtest directory:

```bash
cd scripts/backtest
python main.py
```

### 3. Run Parameter Optimization

The optimizer does a grid search over all `(window, signal)` combinations and returns the Sharpe ratio for each:

```python
window_list = tuple(range(0, 50000, 1000))
signal_list = tuple(np.arange(0, 2.5, 0.25))

param_opt = ParametersOptimization(
    ta.data,
    trading_period,
    ta.get_bollinger_band,          # indicator function
    strat.momentum_const_signal     # strategy function
)

results = pd.DataFrame(param_opt.optimize(window_list, signal_list))
results.rename(columns={0: 'window', 1: 'signal', 2: 'sharpe'}, inplace=True)
```

This produces a Sharpe heatmap (`window` x `signal`) so you can visually identify the best parameter region.

### 4. Available Indicators & Strategies

**Indicators** (`ta.py` — all operate on the `factor` column):

| Method | Description |
|---|---|
| `get_sma(period)` | Simple Moving Average |
| `get_ema(period)` | Exponential Moving Average |
| `get_rsi(period)` | Relative Strength Index (0–100) |
| `get_bollinger_band(period)` | Bollinger Z-score: `(factor - SMA) / rolling_std` |
| `get_stochastic_oscillator(period)` | Stochastic %D (requires High/Low/Close columns) |

**Strategies** (`strat.py`):

| Method | Long | Short | Flat |
|---|---|---|---|
| `momentum_const_signal` | indicator > +signal | indicator < -signal | otherwise |
| `reversion_const_signal` | indicator < -signal | indicator > +signal | otherwise |

### 5. Performance Metrics

`perf.py` computes these for both the strategy and a buy-and-hold benchmark:

- **Total Return** — cumulative PnL
- **Annualized Return** — mean PnL per bar x bars per year
- **Sharpe Ratio** — annualized risk-adjusted return
- **Max Drawdown** — largest peak-to-trough decline
- **Calmar Ratio** — mean return / max drawdown
- **Transaction costs** — 0.05% per unit of turnover (built into PnL)

---

## Going Live: From Backtest to Production

Once you find optimal parameters from the backtest, apply them to the live scripts:

### 1. Transfer Parameters

Take the best `(window, signal)` pair from your optimization heatmap and set them as `x` and `y` in `scripts/bybit._trade.py`:

```python
# In bybit._trade.py — set these to your optimized values
x = 3          # rolling window (from backtest optimization)
y = 0          # z-score threshold (from backtest optimization)
bet_size = 0.001   # position size in BTC
```

### 2. Start the Data Collector

In one terminal, start the live data feed:

```bash
cd scripts
python bybit_trade_data.py
```

This polls Bybit every minute at second 0, fetches the last 100 BTCUSDT 1-minute candles, and appends new rows to `data.csv`.

### 3. Start the Trading Bot

In a second terminal, start the trading loop:

```bash
cd scripts
python bybit._trade.py
```

This reads `data.csv` at second 5 each minute, computes the rolling z-score with your parameters, and places market orders on Bybit:
- **z > y** → long (buy `bet_size`)
- **z <= y** → flat (sell to close if holding)

### How the Live Signal Works

The live script replicates the Bollinger Z-score from the backtest:

```
z = (close - rolling_mean(x)) / rolling_std(x)
```

If `z > y`, it goes long. Otherwise it flattens to zero. It checks current position size on Bybit before each trade to avoid duplicate orders.

---

## Data Sources

| Source | Asset Classes | Used In |
|---|---|---|
| **Glassnode** | Crypto (BTC, ETH, etc.) | Backtest — historical price & on-chain factors |
| **Futu OpenD** | HK & US equities | Backtest — historical OHLCV (requires Futu desktop client) |
| **Bybit (ccxt)** | Crypto derivatives | Live trading — real-time 1m candles + order execution |

---

## Environment Variables

Create `scripts/.env` with:

```
GLASSNODE_API_KEY=...
FUTU_HOST=127.0.0.1
FUTU_PORT=11111
BYBIT_API_KEY=...
BYBIT_SECRET_KEY=...
```

---

## Notebooks

| Notebook | Purpose |
|---|---|
| `btc_bband_analysis.ipynb` | Bollinger Band analysis on BTC |
| `btc_flow_exchange_analysis.ipynb` | Exchange netflow analysis |
| `param_opt.ipynb` | Parameter optimization experiments |
| `futuapi.test.ipynb` | Futu API integration testing |
| `test.ipynb` / `test_2.ipynb` | General exploration |
