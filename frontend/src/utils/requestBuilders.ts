import type { BacktestConfig, OptimizeRequest, PerformanceRequest, Top10Row } from '../types/backtest';
import { isSingleFactorRow, multiFactorParams } from './top10';

export function effectiveSymbol(cfg: BacktestConfig): string {
  return cfg.vendorSymbol || cfg.symbol;
}

export function buildOptimizeRequest(cfg: BacktestConfig): OptimizeRequest {
  const f0 = cfg.factors[0];
  const ds = cfg.dataSource || undefined;
  const base = {
    symbol: effectiveSymbol(cfg), start: cfg.start, end: cfg.end,
    trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps, data_source: ds,
    refresh_dataset: cfg.refreshDataset,
    walk_forward: cfg.walkForward, split_ratio: cfg.splitRatio,
  };
  if (cfg.factors.length <= 1) {
    return {
      ...base, mode: 'single' as const,
      indicator: f0.indicator, strategy: f0.strategy,
      window_range: f0.window_range, signal_range: f0.signal_range,
    };
  }
  return {
    ...base, mode: 'multi' as const,
    conjunction: cfg.conjunction, factors: cfg.factors,
  };
}

export function buildPerformanceRequest(cfg: BacktestConfig, row: Top10Row): PerformanceRequest {
  const f0 = cfg.factors[0];
  const ds = cfg.dataSource || undefined;
  if (cfg.factors.length <= 1) {
    if (!isSingleFactorRow(row)) {
      throw new Error('buildPerformanceRequest: single-factor config requires a single-factor row');
    }
    return {
      symbol: effectiveSymbol(cfg), start: cfg.start, end: cfg.end,
      mode: 'single', trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps,
      data_source: ds, refresh_dataset: cfg.refreshDataset,
      indicator: f0.indicator, strategy: f0.strategy,
      window: row.window, signal: row.signal,
    };
  }
  const { windows, signals } = multiFactorParams(row);
  return {
    symbol: effectiveSymbol(cfg), start: cfg.start, end: cfg.end,
    mode: 'multi', trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps,
    data_source: ds, refresh_dataset: cfg.refreshDataset,
    conjunction: cfg.conjunction, factors: cfg.factors,
    windows, signals,
  };
}
