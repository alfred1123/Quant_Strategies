# Return Compounding — `cumu` summed simple returns instead of compounding

!!! note "Archived"
    Bug **fixed** in `quant/strategy/performance.py`. Old `BT.RESULT` rows may still use the pre-fix convention.

!!! success "Fixed in `quant/strategy/performance.py`"
    `_compound()` builds an equity curve with `cumprod` and reads drawdown off
    it; `_cagr()` replaces the arithmetic annualisation. `Total Return`,
    `Annualized Return`, `Max Drawdown`, `Calmar Ratio` and the equity-curve
    chart are now real capital growth. **Sharpe never changed** — it reads the
    per-bar series and was correct throughout. The 36 rows already in
    `BT.RESULT` are on the old convention and are being re-run (see
    [Stored results](#stored-results-still-on-the-old-convention)).

**Related:** [Plan to Profit](../design/plan-to-profit.md), [Best-VID Promotion](../design/best-vid-promotion.md),
[Backtest Queue](../design/backtest-queue.md)

---

## The defect

```python
self.data["chg"]  = self.data["price"].pct_change()   # simple returns
self.data['pnl']  = FinalPosition_x1 * chg - trade * transaction_cost
self.data['cumu'] = self.data['pnl'].cumsum()         # ← additive
self.data['dd']   = self.data['cumu'].cummax() - self.data['cumu']
```

`cumsum` is a perfectly ordinary backtest primitive — but only on **log**
returns, which are additive by construction. There are two self-consistent
conventions and this code used neither:

| Convention | Per-bar return | Accumulate | Equity |
|---|---|---|---|
| Log | `ln(P_t / P_t-1)` | `cumsum` | `exp(cumsum)` |
| Simple | `P_t / P_t-1 - 1` | `cumprod` | `cumprod(1 + r)` |

`chg` came from `pct_change()`, so `pnl` was a simple per-bar return and
summing it produced a number in no units at all. Summing simple returns
approximates compounding only when returns are small and the horizon is short;
on multi-year crypto dailies it is neither.

A second, unambiguous symptom: `dd` as `cummax - cumu` on an additive series
approximates `-ln(1 - true_drawdown)` and is **unbounded**.
`BUY_HOLD_MAX_DRAWDOWN` for the deployed BTC strategy read **1.2243** — a 122%
drawdown on a long-only position, which is impossible. **6 of 36** stored
results carry `MAX_DRAWDOWN > 1`.

## The fix

```python
def _compound(pnl: pd.Series) -> tuple[pd.Series, pd.Series]:
    equity = (1.0 + pnl).clip(lower=0.0).cumprod()
    peak = equity.cummax().clip(lower=1.0)
    return equity - 1.0, 1.0 - equity / peak
```

Both clips exist for a reason, and neither binds on a well-behaved long-only run:

- **`clip(lower=0.0)` on gross return** floors a ruined position at zero equity.
  A short losing more than 100% on one bar would otherwise make `1 + pnl`
  negative and flip the sign of every later bar.
- **`clip(lower=1.0)` on the peak** anchors the high-water mark at the starting
  capital. `cummax` alone starts at the first bar's equity, so a strategy
  underwater from bar one would report *no* drawdown until it first recovered.

Applied identically to the strategy and buy-and-hold series, which is the whole
reason it is a shared helper rather than two inline expressions.

### Annualised return is now geometric

`get_annualized_return` was `pnl.mean() * trading_period` — an arithmetic
annualisation of an average the capital never actually earned. With a real
equity curve available it became a CAGR:

```python
def _cagr(pnl: pd.Series, trading_period: int) -> float:
    n = int(pnl.notna().sum())
    if n == 0:
        return np.nan
    equity = float((1.0 + pnl).clip(lower=0.0).prod())
    return equity ** (trading_period / n) - 1.0
```

The horizon `n` counts finite bars, so warmup `NaN`s do not stretch it. This
was not strictly part of the compounding defect — the arithmetic figure read
the per-bar series and was internally consistent — but leaving it would have
had `CALMAR_RATIO` divide an arithmetic numerator by a compounded denominator.

**The correction does not have a fixed sign**, which is why it is worth stating
rather than assuming it lowers everything. Two forces pull opposite ways:
compounding raises the figure, and volatility drag lowers it. For the deployed
BTC strategy the arithmetic 35.4% becomes **38.6%**, because it is in cash 84%
of the time and compounding dominates; for buy-and-hold over the same window
49.0% becomes **38.8%**, because a 76.7% drawdown makes drag dominate.

## Measured effect

Deployed BTC parameters (`get_bollinger_band`, window 55, signal 1.75,
`momentum_band_signal_long_only`, 10 bps) replayed over `2020-03-25` →
`2026-09-12`, BTC close **$6,698 → $77,245**:

| | Before | After |
|---|---|---|
| Strategy total return | +224.0% | **+686.1%** |
| Strategy annualised | 35.4% *(arithmetic)* | **38.6%** *(CAGR)* |
| Strategy max drawdown | 0.2080 | **19.4%** |
| Strategy Calmar | 1.83 | **1.99** |
| Strategy Sharpe | 1.481 | **1.481** — unchanged |
| Buy & hold total return | +310.0% | **+694.0%** |
| Buy & hold annualised | 49.0% *(arithmetic)* | **38.8%** *(CAGR)* |
| Buy & hold max drawdown | **1.2243** *(impossible)* | **76.7%** |
| Buy & hold Calmar | 0.64 | **0.51** |

The buy-and-hold drawdown of 76.7% is the decisive check: it reproduces BTC's
real November-2021 → November-2022 peak-to-trough almost exactly. Buy-and-hold
total return is 694% rather than the full series' 1,053% because `buy_hold` is
masked to `NaN` during indicator warmup, so both curves are measured over the
same window.

The fixed numbers also tell a different story than the broken ones did. At
38.6% against 38.8%, the strategy roughly **matches** buy-and-hold on return
while taking **a quarter of the drawdown** — 19.4% against 76.7%, a Calmar of
1.99 against 0.51. That is the actual case for running it, and the additive
series had obscured it: the old figures showed the strategy *trailing*
buy-and-hold on return (224% against 310%) while reporting a drawdown
comparison that was meaningless because one side exceeded 100%.

## Sharpe was, and remains, correct

`pnl.mean() / pnl.std() * sqrt(trading_period)` reads the per-bar series and
never touches `cumu`, so it is structurally immune to a defect in how bars are
accumulated. Verified by independent SQL replay of the same parameters: 1.436
against the stored 1.481, the gap being warmup and window edges.

Three properties are **conventions rather than errors**, worth stating because
Sharpe is the promotion objective and gets compared against total return:

- **Risk-free rate is zero.** It is an `rf = 0` Sharpe, standard for crypto. The
  distortion is smaller than it looks: the strategy is in cash 84% of the time
  (388 of 2,361 bars in market), and a proper excess return on those days would
  be `rf - rf = 0`, exactly what the model already records. Only the days in
  market are overstated, by a daily risk-free rate each.
- **Simple returns in the numerator.** Feeding log returns to the same formula
  gives 1.336 rather than 1.436, about 7% lower. Both are defensible; simple is
  the more common choice.
- **`sqrt(trading_period)` scaling assumes i.i.d. returns.** Momentum strategies
  are autocorrelated, which biases the annualisation. Standard practice, but not
  free.

### Sharpe is the optimisation objective, so the reported figure is biased high

`quant/strategy/objective.py` maximises Sharpe across the window × signal grid,
so what gets stored is the maximum of many noisy estimates — upward-biased by
selection, and by more when the grid is larger. The sampling error is wide on
its own terms: 54 round trips over 6.5 years, and the i.i.d. approximation
`sqrt((1 + SR²/2) / n)` puts annualised Sharpe at roughly **1.44 ± 0.39**, a 95%
interval spanning about 0.65 to 2.2.

Correctly computed, in other words, but carrying far less precision than three
decimal places imply. [`MIN_METRIC_OBS`](../decisions.md) (decision #63) guards
the degenerate end of this; it does not address selection bias.

## Blast radius

| Surface | Impact |
|---|---|
| `quant/strategy/performance.py` | `cumu`, `dd`, `buy_hold_cumu`, `buy_hold_dd`, `get_total_return`, `get_max_drawdown`, `get_calmar_ratio`, `get_annualized_return` |
| `BT.RESULT` columns | `TOTAL_RETURN`, `ANNUALIZED_RETURN`, `MAX_DRAWDOWN`, `CALMAR_RATIO` + all four `BUY_HOLD_*` twins (36 rows, 24 strategies) |
| `REFDATA.PROMOTION_METRIC` | HARD `max_dd_gate` (`Max Drawdown <= 0.40`); SOFT ranking on `calmar_compare`, `total_return`, `max_drawdown` |
| Frontend | `EquityCurveChart` — no code change; `pct()` and the "(%)" axis titles were already right, the values feeding them now are too |
| Fitted parameters | **None.** The optimizer maximises Sharpe alone, so no stored `WINDOW` / `SIGNAL` was chosen on a wrong number |
| Live signal generation | **None.** `compute_latest_position` uses `FinalPosition`, produced before any PnL column exists |

### The promotion gate now means what it says — and is deliberately looser

`max_dd_gate` is HARD at `0.40`. Against the additive series it rejected
strategies whose *true* drawdown was about 33%, because additive drawdown
overstates. Against the fixed series it rejects a real 40%, so the effective
gate loosened by roughly 7 points of real drawdown.

**`0.40` is kept.** The option to re-tighten to `0.33` — preserving the old
effective strictness — was considered and rejected: a real 40% cap is the
intended risk limit, and the previous 33% was an artefact of the defect rather
than a choice anyone made. The label `Max DD LTE 40%` is now accurate, and no
`REFDATA.PROMOTION_METRIC` change is needed.

SOFT ranking is largely preserved: the additive → compounded transform is
monotonic within a series, so candidate-vs-best ordering rarely flips. That is
why the defect never produced visible chaos — the numbers were wrong, the
decisions mostly were not.

## Stored results, still on the old convention

The 36 existing `BT.RESULT` rows cannot be recomputed in SQL: `PAYLOAD_JSON`
holds the metric dicts, but rebuilding an equity curve needs the per-bar
position series, which is not stored. This matters because promotion compares a
candidate against the stored current best, and a new-convention candidate
against an old-convention best is a corrupted comparison.

**Decision: re-run all 36 through the queue.** It is the only option that leaves
every stored metric on one convention, which is what promotion comparisons
require. Invalidating and recomputing lazily was rejected because it leaves the
mixed state live in the meantime — exactly the corrupted comparison the re-run
exists to prevent — and accepting the discontinuity was rejected because
`BT.RESULT` is what the promotion path reads, not an archive.

The cost is accepted: re-running mints new `RESULT_VID`s and takes queue time.
Replay is safe because every stored `CONFIG_JSON` carries the full request
(`data_source` since decision #53, `tm_interval_id` since #57), so each result
is reproducible from its own row.

`scripts/rerun_results.py` drives it:

```bash
python -m scripts.rerun_results --user-id <uuid> --dry-run
python -m scripts.rerun_results --user-id <uuid> [--user-id <uuid>]
```

Each job is enqueued against the **same** `(STRATEGY_ID, STRATEGY_VID)` as the
result it replaces, so no new strategy version is minted, and as the strategy's
owner, so it lands in that user's job list and counts against that user's cap.

Three properties are worth knowing before running it:

- **Order matters.** Run it only once the new `quant-app` image is serving. The
  worker computes the metrics, so a replay against the old image regenerates
  the old numbers — and the script would then read the fresh timestamp and
  consider the row done.
- **It is re-runnable.** Only versions whose current result predates
  `--cutover` (default: now) are enqueued. `MAX_QUEUED_PER_USER` is 30 against
  36 results, so the first pass defers the remainder and reports the count;
  invoke again once the queue drains. The cap is not bypassed — it is what
  stops one submitter starving the queue, and a backfill has no claim on it.
- **Logically deleted strategies are skipped.** `SP_GET_STRATEGY_LIST` omits
  them by design (decision #66). One of the 36 is retired, so a complete
  migration covers 35; its promotion history keeps the old figures.

## Verification

Covered by `tests/unit/test_perf.py::TestCompound` and the drawdown assertions
in `TestPerformanceInit` / `TestStrategyMetrics`:

1. A series where sum and product diverge — `+50%, -50%` sums to `0.0` and
   compounds to `-0.25`.
2. Drawdown bounded — `0 <= dd <= 1` over a 2,000-bar random walk.
3. Drawdown measured from starting capital when the curve never exceeds it.
4. Ruin floors at a total loss instead of flipping sign.
5. Regression: fee-free always-long buy-and-hold equals `last_px / first_px - 1`.
6. End-to-end replay of the deployed BTC parameters reproduces BTC's real 76.7%
   buy-and-hold drawdown.

`TestCagr` covers the annualisation separately: a constant rate annualises to
its own compounded year, a doubling over two years gives `sqrt(2) - 1`, a
varying series falls below its arithmetic annualisation, warmup `NaN`s do not
stretch the horizon, and ruin gives `-100%`.
