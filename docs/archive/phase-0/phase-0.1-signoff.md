# Phase 0.1 — Walk-Forward Sign-Off

**Date:** 2026-05-20  
**Verdict:** **WATCH** — promote config to Trade picker for dry-run / paper only; defer live apply (Phase 1.7) until OOS Sharpe improves or Phase 2 reconcile confirms live edge.

**Tooling:** Existing pipeline only — `quant.strategy.walk_forward.WalkForward` + grid search (`ParametersOptimization`). Price via Yahoo `BTC-USD` (vendor proxy for `btcusdt.crypto`). No new scripts.

---

## Live candidate

| Field | Value |
|-------|-------|
| `internal_cusip` | `btcusdt.crypto` |
| Indicator | `get_bollinger_band` on **price** |
| Strategy | `momentum_band_signal` |
| Window / signal | **60 / 1.75** |
| Date range | 2016-01-01 → 2026-05-16 (3788 daily bars) |
| Fee | 5 bps |
| Grid (full-period opt) | window 10–100 step 5 × signal 0.25–2.5 step 0.25 → **190/190** valid trials |
| Config label | `bollinger_momentum_60_1.75` |

`strategy_id` (UUID) is assigned when this config is saved via the backtest queue / `BT.SP_INS_STRATEGY` — use that row as the Trade picker reference in Phase 1.6.

---

## Full-period optimization (in-sample research)

| Metric | Value |
|--------|-------|
| Best params | window=60, signal=1.75 |
| Sharpe | **1.1876** |
| Total return | 4.91 |
| Max drawdown | 0.34 |

Matches the UI optimization run referenced in planning notes.

---

## Fixed-params holdout (70% IS / 30% OOS)

Params frozen at 60 / 1.75 — no re-optimization on OOS.

| Split | Period | Bars | Sharpe | Ann. return | Max DD |
|-------|--------|------|--------|-------------|--------|
| Full | 2016-01-01 → 2026-05-15 | 3788 | **1.19** | 0.48 | 0.34 |
| IS 70% | 2016-01-01 → 2023-04-04 | 2651 | **1.43** | 0.64 | 0.31 |
| OOS 30% | 2023-04-05 → 2026-05-15 | 1137 | **0.42** | 0.12 | 0.34 |

OOS Sharpe is **positive but well below** the plan’s expected live Sharpe (~1.08). Edge in the recent regime is materially weaker than full history.

---

## Walk-forward (re-optimize on IS, test on OOS)

Grid identical to full-period optimization.

### Split 0.5 (50% IS / 50% OOS)

| | IS | OOS |
|--|----|-----|
| Best params | window=90, signal=2.0 | (same, applied to OOS) |
| Sharpe | 1.90 | **−0.09** |
| Overfitting ratio | | **1.05** |

### Split 0.7 (70% IS / 30% OOS)

| | IS | OOS |
|--|----|-----|
| Best params | window=65, signal=1.5 | (same, applied to OOS) |
| Sharpe | 1.45 | **−0.13** |
| Overfitting ratio | | **1.09** |

Re-optimized IS params **do not generalize** to the OOS window — negative OOS Sharpe under walk-forward. Recent market regime does not support the in-sample optimum.

---

## Go / no-go / watch rationale

| Gate | Threshold | Result |
|------|-----------|--------|
| Full-period Sharpe | research reference ~1.2 | **Pass** (1.19) |
| Fixed-params OOS Sharpe | expected live ~1.08 | **Fail** (0.42) |
| Walk-forward OOS Sharpe | &gt; 0 | **Fail** (negative) |

**WATCH** because:

1. Fixed 60/1.75 still earns positive OOS Sharpe (0.42) — not a dead strategy.
2. Walk-forward and fixed OOS both show **recent degradation** vs full history.
3. Safe path: allow **dry-run / paper** in Phase 1.3–1.6; block **live apply** (1.7) until Phase 2 reconcile or a fresh optimization on a recent window passes WF.

---

## Reproduce

```bash
# Walk-forward (CLI — uses btc-usd cusip from Yahoo symbol)
python -m quant.cli --symbol BTC-USD --start 2016-01-01 --end 2026-05-16 \
  --indicator bollinger --strategy momentum --walk-forward --split 0.7

# Full-period grid + single backtest at defaults (window 20 / signal 1.0)
python -m quant.cli --symbol BTC-USD --start 2016-01-01 --end 2026-05-16 \
  --window 60 --signal 1.75 --no-grid
```

Programmatic run (exact `btcusdt.crypto` cusip) matches numbers in this doc — see commit / session notes.

---

*Phase 0.1 exit criteria met: written WF/OOS metrics + config confirmed for Trade picker. Live `strategy_id` = UUID from next saved backtest run with this config.*
