# TODO

## Overall

1. Unit testing for all scripts
2. Integration test
3. CI/CD to deploy to production


## SQLite (database: TradeBros)

1. Store datasource metadata and **requirements** for what to persist; minimize repeat API queries. Each stored requirement should point at the dataset it produced.

    REFDATA.APP

    | APP_ID | NAME | DESCRIPTION | USER_ID | UPDATE_DB_TS |
    |--------|------|-------------|---------|--------------|
    | 1 | Futu API | Futu Trade API | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 2 | Alphavantage | Alphavantage | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |

    REFDATA.TM_INTERVAL

    | TM_INTERVAL_ID | NAME | DESCRIPTION | USER_ID | UPDATE_DB_TS |
    |----------------|------|-------------|---------|--------------|
    | 1 | Daily | Daily Closing Price | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |

    REFDATA.ORDER_STATE

    | ORDER_STATE_ID | NAME | DESCRIPTION | USER_ID | UPDATE_DB_TS |
    | --- | --- | --- | --- | --- |
    | 1 | NEW | Order has been created but not yet sent | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 2 | PENDING | Order submitted, awaiting processing | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 3 | PARTIALLY_FILLED | Order partially executed | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 4 | FILLED | Order fully executed | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 5 | CANCELLED | Order cancelled before execution | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 6 | REJECTED | Order rejected by system or exchange | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |

    REFDATA.TRANS_STATE

    | TRANS_STATE_ID | NAME | DESCRIPTION | USER_ID | UPDATE_DB_TS |
    | --- | --- | --- | --- | --- |
    | 1 | PENDING | Transaction created, not yet processed | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 2 | COMPLETED | Transaction successfully completed | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 3 | FAILED | Transaction failed due to error | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |

    REFDATA.API_LIMIT — record rate limits and quotas per data source so the pipeline can throttle automatically.

    | API_LIMIT_ID | APP_ID | LIMIT_TYPE | MAX_VALUE | TIME_WINDOW_SEC | DESCRIPTION | USER_ID | UPDATE_DB_TS |
    |--------------|--------|------------|-----------|-----------------|-------------|---------|--------------|
    | 1 | 2 | RATE | 1 | 1 | 1 request per second (free tier) | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 2 | 2 | DAILY_QUOTA | 25 | 86400 | 25 requests per day (free tier) | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 3 | 2 | OUTPUT_SIZE | 100 | NULL | Compact mode returns ~100 most recent trading days only | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |

    BACKTEST.API_REQUEST

    | API_REQ_ID | API_REQ_VID | APP_ID | TM_INTERVAL_ID | SYMBOL | IS_CURRENT_IND | RANGE_START_TS | RANGE_END_TS | STORAGE_PATH | API_REQ_PAYLOAD | USER_ID | CREATED_AT |
    |------------|-------------|--------|----------------|--------|----------------|----------------|--------------|--------------|-----------------|--------|------------|
    | UUID | 1 | 2 | 1 | BTCUSDT | Y | 2010-01-01T00:00:00Z | 2026-01-01T00:00:00Z | /data/raw/alphavantage | `{"filter1":"xxx","filter2":"xxx","filterdate":{"from":"...","to":"..."}}` | alfcheun | 2026-03-30T12:00:00Z |

    BACKTEST.API_REQUEST_PAYLOAD — normalized storage for large/split responses. `API_REQ_PAYLOAD` on `API_REQUEST` holds inline or summary JSON; use this child table when the payload is large or versioned separately.

    | API_REQ_ID | API_REQ_VID | PAYLOAD | CREATED_AT |
    |------------|-------------|---------|------------|
    | UUID | 1 | {...data...} | CURRENT TIMESTAMP - CURRENT TIMEZONE |

    TRADE.TRANSACTION — `ORDER_STATE_ID` is denormalized here for convenience; consider a dedicated `ORDERS` table if order lifecycle grows.

    | TRANS_ID | APP_ID | ORDER_STATE_ID | TRANS_STATE_ID | SYMBOL | BUY_SELL_CD | TRANS_CCY_CD | QUANTITY | PRICE | NOTIONAL_AMT | FEE_AMT | CREATED_AT |
    |----------|--------|----------------|----------------|--------|-------------|--------------|---------|-------|--------------|---------|------------|
    | UUID | 1 | 2 | 3 | BTCUSDT | B | USDT | 0.015 | 97234.50 | 1458.52 | 0.87 | 2026-03-30T14:22:01Z |
    | UUID | 1 | 2 | 3 | BTCUSDT | S | USDT | 0.010 | 97100.00 | 971.00 | 0.58 | 2026-03-30T15:05:33Z |
    | UUID | 2 | 1 | 1 | ETHUSDT | B | USDT | 0.50 | 1820.75 | 910.38 | 0.55 | 2026-03-30T16:41:12Z |


## Agent

1. Prefer backtests anchored on **daily closing prices** (align rules with that bar).
2. When strategies exist under `scripts/bt/`, surface them as selectable commands or CLI targets to run.

## Trade

1. Redesign trading repository: strategies as objects, loadable from the bt package (shared definitions with live trading).

```
Quant_Strategies/
├── scripts/
│   ├── bt/                  # Backtesting pipeline
│   │   ├── data.py          # Data retrieval (Futu, Glassnode)
│   │   ├── ta.py            # Technical analysis indicators
│   │   ├── strat.py         # Signal generation strategies
│   │   ├── perf.py          # Performance metrics & PnL engine
│   │   ├── param_opt.py     # Grid-search parameter optimization
│   │   ├── main.py          # Backtest entry point — wires everything together
│   │   └── .env
│   │
│   └── .env                     # API keys (gitignored)
├── backup/
│   └── deco/                    # Decommissioned Bybit scripts (kept for reference)
├── notebooks/               # Jupyter exploration & prototyping
├── data/
│   ├── raw/                 # Source datasets (Excel, zips)
│   └── processed/           # Cleaned datasets
├── results/                 # Output charts (PNGs)
├── data.csv                 # Live OHLCV feed (created at runtime)
└── Trading Strategy.html    # Plotly backtest visualization
```

1. Plug in Futu API trade (optional Alphavantage / Glassnode).
2. Start with a crypto pricing strategy.

---

## Code Quality & Robustness

### Error Handling
1. Add try/except around all API calls in `data.py` (Glassnode, Futu) — currently any network failure crashes silently or propagates unhandled.
2. Guard against division-by-zero in `perf.py` (Sharpe denominator, annualized return).
3. Add error handling for future live trading scripts.
4. Validate DataFrame columns exist before accessing (`ta.py` assumes `'factor'`, `'Close'`, `'High'`, `'Low'` without checks).

### Configuration
1. Extract hardcoded parameters from source into a config file (YAML or JSON):
   - Symbol, date range, interval (`main.py`)
   - Indicator window, signal threshold (`main.py`)
   - Trading period constant (`365 * 24 * 6`)
   - Transaction cost (`0.0005` in `perf.py`)
   - Bet size, polling interval (future live trading scripts)
2. Support CLI arguments for `main.py` (e.g. `python main.py --symbol BTC --start 2020-01-01 --end 2025-01-01`).

### Logging
1. Replace all `print()` calls with Python `logging` module — especially in live trading scripts.
2. Add persistent log files for trade execution audit trail (future live trading scripts).
3. Add timestamps and log levels for debugging.

### Code Duplication
1. `perf.py`: Strategy and buy-and-hold metrics are near-identical — refactor into a shared `_compute_metrics(returns)` method.
2. Inline z-score logic in decommissioned trade scripts should be reused from `ta.py` in future live trading.
3. Fix typo: `get_buy_hold_get_annualized_return()` → `get_buy_hold_annualized_return()`.

---

## Architecture & Design

### Data Layer
1. Add a common interface (base class or protocol) for all data sources (`FutuOpenD`, `Glassnode`) so they return a consistent DataFrame schema.
2. Fix `@lru_cache` on instance methods in `data.py` — either use `functools.cached_property` or move to module-level caching.
3. Add input validation on symbols, date ranges, intervals at the data layer boundary.

### Strategy Abstraction
1. Convert `Strategy` static methods to a proper strategy interface (base class with `generate_signal(data, params) -> Series`).
2. Future live trading should import and use the same strategy definitions as backtesting.
3. Add position sizing support beyond fixed `{-1, 0, 1}`.

### Live Trading Reliability
1. When building new live trading integration, use SQLite or an in-memory queue instead of CSV as shared state (lesson from decommissioned Bybit scripts — see `backup/deco/`).
2. Add graceful shutdown (signal handling for SIGINT/SIGTERM) to any live trading loops.
3. Add position reconciliation — check actual exchange position vs. expected before placing orders.
4. Persist trade fills to database (not just stdout).

### Directory Restructure
1. Decommissioned Bybit scripts moved to `backup/deco/` — reuse signal/strategy logic for future integrations.
2. Clean up dead/commented-out code in `main.py` and `ta.py` (commented MACD method, placeholder data merge).

---

## Testing & CI/CD

### Unit Tests
1. Test indicator calculations in `ta.py` against known values (e.g. SMA of `[1,2,3,4,5]` with window 3).
2. Test `perf.py` metrics: Sharpe, max drawdown, Calmar on synthetic return series.
3. Test strategy signals: verify `{-1, 0, 1}` output for known inputs.
4. Test data source classes with mocked API responses.

### Integration Tests
1. End-to-end backtest run with sample data (no live API calls).
2. Validate parameter optimization returns expected grid shape.

### CI/CD Pipeline
1. GitHub Actions workflow: lint (`ruff`/`flake8`), test (`pytest`), on push/PR.
2. Add `pyproject.toml` for standardized project metadata and tool config.
3. Pre-commit hooks for formatting and linting.

---

## Documentation

1. Add inline comments for non-obvious algorithm details (RSI smoothing, Bollinger Z formula).
2. Add a troubleshooting section to README (Futu OpenD connection, API rate limits, common errors).
3. Add type hints to function signatures across all modules.
4. Document the database schema relationships and query patterns (when SQLite is implemented).
