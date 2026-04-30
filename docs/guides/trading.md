# Paper Trading with Futu OpenD

!!! note "Status"
    The Futu paper-trading flow is currently a **Python-only utility** in `src/trade.py`. It is **not exposed in the React SPA** at the moment. Use it from a Python shell, notebook, or script.

## Prerequisites

1. **Install Futu OpenD** — download from [futunn.com](https://www.futunn.com/download/openAPI)
2. **Launch Futu OpenD** — open the desktop app and log in. The gateway must be running whenever you trade.
3. **Enable API access** — in Futu OpenD settings, ensure the API server is enabled (default port: `11111`).
4. **Set env vars** in `.env`:
   ```
   FUTU_HOST=127.0.0.1
   FUTU_PORT=11111
   ```

## From Python

```python
# Run from the src/ directory (or add it to PYTHONPATH)
from trade import FutuTrader

with FutuTrader(paper=True) as trader:
    result = trader.place_order("US.AAPL", 10, "BUY")
    print(result)

    print(trader.get_positions())

    # Apply a backtest signal: +1 = long, -1 = short, 0 = flat
    trader.apply_signal("US.AAPL", signal_value=1, qty=10)

    trader.cancel_all_orders()
```

## Symbol Format

Futu uses prefixed symbols:

- US equities/ETFs: `US.AAPL`, `US.SPY`
- HK equities: `HK.00700`
- Crypto-like contracts vary by region — see Futu OpenD docs.

## Tips

!!! tip
    Futu's paper trading environment simulates realistic fills during market hours. Outside trading hours, market orders will queue until the next session opens.

!!! warning
    Live trading (`paper=False`) places real orders. Always confirm `paper=True` until you have explicitly tested the full pipeline end-to-end.

## Roadmap

A trading panel may be added back to the React SPA in a future phase. Until then, this guide covers the supported entry point.
