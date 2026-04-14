# Paper Trading with Futu OpenD

The **Trading** tab in the Streamlit dashboard lets you connect to a running Futu OpenD gateway and execute orders in paper (simulate) or live mode — directly from your backtest results.

## Prerequisites

1. **Install Futu OpenD** — download from [futunn.com](https://www.futunn.com/download/openAPI)
2. **Launch Futu OpenD** — open the desktop app and log in. The gateway must be running whenever you trade.
3. **Enable API access** — in Futu OpenD settings, ensure the API server is enabled (default port: `11111`).
4. **Set env vars** in `.env`:
   ```
   FUTU_HOST=127.0.0.1
   FUTU_PORT=11111
   ```

## Paper Trading Walkthrough

1. Launch the dashboard: `cd src && streamlit run app.py`
2. Go to the **Trading** tab
3. Configure:
     - **Futu Symbol** — use Futu format: `US.AAPL`, `US.WEAT`, `HK.00700`
     - **Quantity** — number of shares per order
     - **Paper Trading** — toggle ON (enabled by default)
4. Click **Connect to Futu OpenD**

## Placing Orders

**Manual orders:**

- Select Side (BUY/SELL), Type (MARKET/LIMIT), and optionally a Limit Price
- Click **Place Order** — routes to Futu's paper trading environment

**Strategy-driven orders:**

- Set Window and Signal parameters
- Click **Generate Signal & Execute** — the dashboard runs the pipeline on latest data, reads the position signal, and places orders to match

## From Python (without the dashboard)

```python
from trade import FutuTrader

with FutuTrader(paper=True) as trader:
    result = trader.place_order("US.AAPL", 10, "BUY")
    print(result)

    print(trader.get_positions())

    trader.apply_signal("US.AAPL", signal_value=1, qty=10)  # go long

    trader.cancel_all_orders()
```

!!! tip
    Futu's paper trading environment simulates realistic fills during market hours. Outside trading hours, market orders will queue until the next session opens.
