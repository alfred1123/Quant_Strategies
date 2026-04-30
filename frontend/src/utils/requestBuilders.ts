import type { BacktestConfig, OptimizeRequest, PerformanceRequest, Top10Row } from '../types/backtest';
import { isSingleFactorRow, multiFactorParams } from './top10';

export function effectiveSymbol(cfg: BacktestConfig): string {
  return cfg.vendorSymbol || cfg.symbol;
}

/**
 * Build an OptimizeRequest from form state.
 *
 * The backend always accepts the unified factor-list shape. A single
 * factor config is just a 1-element ``factors`` array — there is no
 * "single mode" branch. Cross-product overrides on ``factors[i]``
 * (symbol / vendor_symbol / data_source) flow through unchanged.
 *
 * ``conjunction`` is only included when there are 2+ factors — it is
 * meaningless for a single-factor run, so we omit it from the wire
 * payload to match the backend schema (``conjunction: str | None``).
 */
export function buildOptimizeRequest(cfg: BacktestConfig): OptimizeRequest {
  const ds = cfg.dataSource || undefined;
  return {
    symbol: effectiveSymbol(cfg),
    start: cfg.start,
    end: cfg.end,
    trading_period: cfg.tradingPeriod,
    fee_bps: cfg.feeBps,
    data_source: ds,
    refresh_dataset: cfg.refreshDataset,
    factors: cfg.factors,
    ...(cfg.factors.length > 1 ? { conjunction: cfg.conjunction } : {}),
    walk_forward: cfg.walkForward,
    split_ratio: cfg.splitRatio,
  };
}

/**
 * Build a PerformanceRequest from form state + a selected top-10 row.
 *
 * 1-factor optimizer rows carry plain ``window`` / ``signal``;
 * 2+ factor rows carry ``window_0`` / ``signal_0`` / ... — both shapes
 * collapse to the same ``windows: number[]`` / ``signals: number[]``
 * payload.
 */
export function buildPerformanceRequest(cfg: BacktestConfig, row: Top10Row): PerformanceRequest {
  const ds = cfg.dataSource || undefined;
  let windows: number[];
  let signals: number[];
  if (isSingleFactorRow(row)) {
    if (cfg.factors.length !== 1) {
      throw new Error('buildPerformanceRequest: single-factor row used with multi-factor config');
    }
    windows = [row.window];
    signals = [row.signal];
  } else {
    ({ windows, signals } = multiFactorParams(row));
  }
  if (windows.length !== cfg.factors.length || signals.length !== cfg.factors.length) {
    throw new Error(
      `buildPerformanceRequest: row params length (${windows.length}/${signals.length}) ` +
      `does not match factors length (${cfg.factors.length})`,
    );
  }
  return {
    symbol: effectiveSymbol(cfg),
    start: cfg.start,
    end: cfg.end,
    trading_period: cfg.tradingPeriod,
    fee_bps: cfg.feeBps,
    data_source: ds,
    refresh_dataset: cfg.refreshDataset,
    factors: cfg.factors,
    ...(cfg.factors.length > 1 ? { conjunction: cfg.conjunction } : {}),
    windows,
    signals,
  };
}
