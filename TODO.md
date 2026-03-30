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
2. When strategies exist under `scripts/backtest/`, surface them as selectable commands or CLI targets to run.

## Trade

1. Redesign trading repository: strategies as objects, loadable from the backtest package (shared definitions with live trading).

```
Quant_Strategies/
├── scripts/
│   ├── backtest/            # Backtesting pipeline
│   │   ├── data.py          # Data retrieval (Futu, Glassnode, Bybit)
│   │   ├── ta.py            # Technical analysis indicators
│   │   ├── strat.py         # Signal generation strategies
│   │   ├── perf.py          # Performance metrics & PnL engine
│   │   ├── param_opt.py     # Grid-search parameter optimization
│   │   ├── main.py          # Backtest entry point — wires everything together
│   │   └── .env
│   │
│   ├── trade/
│   │   ├── bybit_trade_data.py  # Live data collector (writes to data.csv)
│   │   ├── bybit._trade.py      # Live trading loop (reads data.csv, places orders)
│   │   ├── prod_data.py         # (WIP) Real-time data class
│   │   └── .env                 # API keys (gitignored)
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
