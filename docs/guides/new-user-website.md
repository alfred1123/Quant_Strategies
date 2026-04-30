# New User Guide: Run a Backtest

This guide walks you through using the Quant Strategies website at [http://52.221.3.230/](http://52.221.3.230/).

## Current Limitations

- **Daily data only** — results are based on daily price data.
- **Vendor symbol must match the data source** — when you type a Vendor Symbol manually, it must match the format expected by the selected data source (for Yahoo Finance: `BTC-USD`, `AAPL`, `0700.HK`).
- **Products and data sources are admin-managed** — the list of available products and data sources is manually entered by the administrator. If a product or source you need is missing, contact your administrator.
- **No email or self-service password reset** — all account changes go through the administrator.

## 1) Login

1. Open [http://52.221.3.230/](http://52.221.3.230/).
2. Enter your **Username** and **Password**.
3. Click **Sign in**.

All user accounts are created and managed by the administrator. If you cannot log in, need a new account, or need any login changes, contact your administrator.

## 2) Open the Configure Panel

After login you will see a page that says **"No results yet"**.

Click the **Configure & Run** button (or the **Configure** button in the top bar) to open the settings panel.

## 3) Choose Your Product

In the settings panel, fill in:

1. **Product** — pick from the dropdown list, or
2. **Vendor Symbol** — type the symbol directly using the format expected by the data source (e.g. `BTC-USD`, `AAPL`, `0700.HK` for Yahoo Finance).
3. **Data Source** — pick the source for this run (admin controls which sources are enabled).

If the product you want is not in the list, enter it manually in the Vendor Symbol field, or ask your administrator to add it.

## 4) Set Date Range and Asset Type

1. **Start** — the start date for your backtest.
2. **End** — the end date (defaults to today).
3. **Asset Type** — select the type that matches your product (e.g. Crypto, US Equity, HK Equity).

## 5) Configure Your Strategy (Factor Card)

Each backtest needs at least one factor. Fill in:

1. **Indicator** — the technical indicator to use (e.g. SMA, EMA, RSI, Bollinger).
2. **Strategy** — the trading rule (e.g. **Momentum** or **Reversion**).
3. **Data Column** — choose Price or Volume.
4. **Window Range** — set Min, Max, and Step for the lookback window.
5. **Signal Range** — set Min, Max, and Step for the signal threshold.

If you are new, leave the ranges at their default values.

You can optionally add a second factor by clicking **+ Add Factor** and choosing a **Conjunction** (AND, OR, or FILTER) to combine them.

## 6) Other Options (Optional)

- **Fee (bps)** — trading fee in basis points (default is fine for most tests).
- **Refresh dataset** — check this to re-download fresh data; leave unchecked to use cached data.
- **Walk-Forward** — runs an overfitting test that splits data into training and testing periods. **On by default**; uncheck to skip.

## 7) Run the Backtest

1. Review the trial count shown at the bottom of the panel.
2. Click **Run Optimization**.
3. Wait for the progress bar to finish — do not close or refresh the page.

## 8) Read the Results

When the run completes, you will see:

- **Summary bar** — shows your symbol, date range, and best Sharpe ratio found.
- **Top 10 table** — the best parameter combinations ranked by performance. Click any row to see its detailed analysis.
- **Analysis panel** — shows:
    - Performance metrics (return, Sharpe, drawdown, etc.)
    - Equity Curve chart
    - Heatmap (for single-factor runs)
    - Walk-Forward comparison (if enabled)
- **Export CSV** — click to download detailed results.

## 9) Compare Different Setups

To compare ideas:

1. Click **Re-configure** (or **Configure** in the top bar).
2. Change one setting (e.g. a different indicator or date range).
3. Run again and compare the new results against the previous run.

## Need Help?

For any questions, access issues, or product requests, contact your administrator.
