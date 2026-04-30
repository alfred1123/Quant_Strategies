import { describe, it, expect } from 'vitest';
import { effectiveSymbol, buildOptimizeRequest, buildPerformanceRequest } from './requestBuilders';
import type { BacktestConfig, Top10Row } from '../types/backtest';

function baseCfg(overrides: Partial<BacktestConfig> = {}): BacktestConfig {
  return {
    symbol: 'btcusdt.crypto', vendorSymbol: '', dataSource: 'yahoo',
    start: '2020-01-01', end: '2024-01-01', assetType: 'Crypto',
    tradingPeriod: 365, feeBps: 5, mode: 'single',
    indicator: 'sma', strategy: 'crossover',
    windowRange: { min: 5, max: 100, step: 5 },
    signalRange: { min: 0.25, max: 2.5, step: 0.25 },
    conjunction: 'AND', refreshDataset: false,
    walkForward: false, splitRatio: 0.5,
    factors: [{
      indicator: 'sma', strategy: 'crossover', data_column: 'price',
      window_range: { min: 5, max: 100, step: 5 },
      signal_range: { min: 0.25, max: 2.5, step: 0.25 },
    }],
    ...overrides,
  };
}

describe('effectiveSymbol', () => {
  it('returns vendorSymbol when set', () => {
    expect(effectiveSymbol(baseCfg({ vendorSymbol: 'BTC-USD' }))).toBe('BTC-USD');
  });
  it('falls back to symbol when vendorSymbol is empty', () => {
    expect(effectiveSymbol(baseCfg())).toBe('btcusdt.crypto');
  });
});

describe('buildOptimizeRequest', () => {
  it('builds single-factor request', () => {
    const req = buildOptimizeRequest(baseCfg());
    expect(req.mode).toBe('single');
    expect(req.indicator).toBe('sma');
    expect(req.strategy).toBe('crossover');
    expect(req.window_range).toEqual({ min: 5, max: 100, step: 5 });
    expect(req.factors).toBeUndefined();
  });

  it('builds multi-factor request', () => {
    const cfg = baseCfg({
      factors: [
        { indicator: 'sma', strategy: 'crossover', data_column: 'price',
          window_range: { min: 5, max: 50, step: 5 }, signal_range: { min: 0, max: 0, step: 1 } },
        { indicator: 'rsi', strategy: 'threshold', data_column: 'price',
          window_range: { min: 10, max: 30, step: 5 }, signal_range: { min: 20, max: 80, step: 10 } },
      ],
    });
    const req = buildOptimizeRequest(cfg);
    expect(req.mode).toBe('multi');
    expect(req.conjunction).toBe('AND');
    expect(req.factors).toHaveLength(2);
    expect(req.indicator).toBeUndefined();
  });

  it('includes walk_forward and split_ratio', () => {
    const req = buildOptimizeRequest(baseCfg({ walkForward: true, splitRatio: 0.6 }));
    expect(req.walk_forward).toBe(true);
    expect(req.split_ratio).toBe(0.6);
  });

  it('omits dataSource as undefined when empty', () => {
    const req = buildOptimizeRequest(baseCfg({ dataSource: '' }));
    expect(req.data_source).toBeUndefined();
  });
});

describe('buildPerformanceRequest', () => {
  it('builds single-factor perf request with row params', () => {
    const row: Top10Row = { window: 20, signal: 1.0, sharpe: 2.5 };
    const req = buildPerformanceRequest(baseCfg(), row);
    expect(req.mode).toBe('single');
    expect(req.window).toBe(20);
    expect(req.signal).toBe(1.0);
  });

  it('builds multi-factor perf request extracting window_/signal_ keys', () => {
    const cfg = baseCfg({
      factors: [
        { indicator: 'sma', strategy: 'crossover', data_column: 'price',
          window_range: { min: 5, max: 50, step: 5 }, signal_range: { min: 0, max: 0, step: 1 } },
        { indicator: 'rsi', strategy: 'threshold', data_column: 'price',
          window_range: { min: 10, max: 30, step: 5 }, signal_range: { min: 20, max: 80, step: 10 } },
      ],
    });
    const row: Top10Row = { window_0: 10, signal_0: 0, window_1: 14, signal_1: 30, sharpe: 1.8 };
    const req = buildPerformanceRequest(cfg, row);
    expect(req.mode).toBe('multi');
    expect(req.windows).toEqual([10, 14]);
    expect(req.signals).toEqual([0, 30]);
  });
});
