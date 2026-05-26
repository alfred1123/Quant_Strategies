# Paper Trading with Futu OpenD

!!! note "Status"
    Futu trading is a **Python utility** today (`quant/futu_trader.py`). It is **not wired to the React Trade UI** yet. For the full OOP integration plan (adapters, worker, deployments), see **[Futu Trading — OOP Implementation](../design/futu-trading.md)**.

## Prerequisites

1. **Install Futu OpenD** — download from [futunn.com](https://www.futunn.com/download/openAPI)
2. **Launch Futu OpenD** — open the desktop app and log in. The gateway must be running whenever you trade.
3. **Enable API access** — in Futu OpenD settings, ensure the API server is enabled (default port: `11111`).
4. **Set env vars** in `.env`:
   ```
   FUTU_HOST=127.0.0.1
   FUTU_PORT=11111
   ```

See also the [official Program Samples](https://openapi.futunn.com/futu-api-doc/en/quick/demo.html) (`OpenSecTradeContext`, `TrdEnv.SIMULATE`).

## From Python

```python
# Run from the project root
from quant.futu_trader import FutuTrader

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

Live deployments will map `internal_cusip` → Futu code via `INST.PRODUCT_XREF` (see [Futu Trading design](../design/futu-trading.md)).

## Tips

!!! tip
    Futu's paper trading environment simulates realistic fills during market hours. Outside trading hours, market orders will queue until the next session opens. Community robots such as [futubot](https://github.com/quincylin1/futubot) often use **limit** orders in paper mode because market orders may not fill immediately.

!!! warning
    Live trading (`paper=False`) places real orders and requires `unlock(trade_password)`. Always confirm `paper=True` until you have explicitly tested the full pipeline end-to-end.

## Roadmap

| Phase | Deliverable |
|-------|-------------|
| A–B | `FutuAdapter` + `AdapterRegistry` under `quant/trade/brokers/futu/` |
| C | Dry-run endpoint + `DeploymentExecutor` |
| D–E | Config credentials, paper/live apply via Trade UI |

Details: [Futu Trading — OOP Implementation](../design/futu-trading.md).
