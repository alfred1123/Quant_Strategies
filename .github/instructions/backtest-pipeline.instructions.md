---
description: "Use when modifying or extending the backtest pipeline: data sources, technical indicators, strategies, performance metrics, or parameter optimization. Covers module interfaces and data flow."
applyTo: "quant/**"
---
# Backtest Pipeline Rules

## Data Flow

```
quant/data/sources.py → quant/strategy/indicators.py → quant/strategy/signals.py
  → quant/strategy/performance.py → quant/strategy/param_opt.py → quant/strategy/walk_forward.py
```

Entry point: `python -m quant.cli` (`quant/cli.py`).

## StrategyConfig

`StrategyConfig` (in `quant/strategy/signals.py`) is a frozen dataclass that packages the strategy identity — reusable across backtest and live trading:

```python
from quant.strategy.signals import StrategyConfig, SignalDirection, SubStrategy

config = StrategyConfig(
    internal_cusip="btc-usd.crypto",
    indicator_name="get_bollinger_band",
    signal_func=SignalDirection.momentum_band_signal,
    trading_period=365,
)
```

## Adding an indicator

Add a method to `TechnicalAnalysis` in `quant/strategy/indicators.py`. Register in `INDICATORS` dict in `quant/cli.py` if exposed via CLI.

## Adding a strategy

Add a static method on `SignalDirection` in `quant/strategy/signals.py`. Register in `STRATEGIES` dict in `quant/cli.py`.

## Testing

After changes under `quant/`, update `tests/unit/` and run `python -m pytest tests/ -v`.
