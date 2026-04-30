import { describe, it, expect } from 'vitest';
import { effectiveSymbol, buildOptimizeRequest, buildPerformanceRequest } from './requestBuilders';
import type { BacktestConfig, Top10Row } from '../types/backtest';

function baseCfg(overrides: Partial<BacktestConfig> = {}): BacktestConfig {
  return {
    symbol: 'btcusdt.crypto', vendorSymbol: '', dataSource: 'yahoo',
    start: '2020-01-01', end: '2024-01-01', assetType: 'Crypto',
    tradingPeriod: 365, feeBps: 5,
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
  it('builds a 1-factor request as a single-element factors list and omits conjunction', () => {
    const req = buildOptimizeRequest(baseCfg());
    expect(req.factors).toHaveLength(1);
    expect(req.factors[0].indicator).toBe('sma');
    expect(req.factors[0].strategy).toBe('crossover');
    expect(req.factors[0].window_range).toEqual({ min: 5, max: 100, step: 5 });
    // conjunction is meaningless for 1 factor — must not be sent.
    expect('conjunction' in req).toBe(false);
  });

  it('builds a multi-factor request preserving factor order and includes conjunction', () => {
    const cfg = baseCfg({
      factors: [
        { indicator: 'sma', strategy: 'crossover', data_column: 'price',
          window_range: { min: 5, max: 50, step: 5 }, signal_range: { min: 0, max: 0, step: 1 } },
        { indicator: 'rsi', strategy: 'threshold', data_column: 'price',
          window_range: { min: 10, max: 30, step: 5 }, signal_range: { min: 20, max: 80, step: 10 } },
      ],
    });
    const req = buildOptimizeRequest(cfg);
    expect(req.factors).toHaveLength(2);
    expect(req.factors[1].indicator).toBe('rsi');
    expect(req.conjunction).toBe('AND');
  });

  it('forwards per-factor cross-product overrides', () => {
    const cfg = baseCfg({
      symbol: 'spy.equity_us', vendorSymbol: '', dataSource: 'yahoo',
      factors: [{
        indicator: 'rsi', strategy: 'threshold', data_column: 'price',
        window_range: { min: 14, max: 14, step: 1 },
        signal_range: { min: 70, max: 70, step: 1 },
        symbol: 'vix.equity_us', data_source: 'yahoo',
      }],
    });
    const req = buildOptimizeRequest(cfg);
    expect(req.symbol).toBe('spy.equity_us');
    expect(req.factors[0].symbol).toBe('vix.equity_us');
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
  it('builds a 1-factor perf request from a single-factor row and omits conjunction', () => {
    const row: Top10Row = { window: 20, signal: 1.0, sharpe: 2.5 };
    const req = buildPerformanceRequest(baseCfg(), row);
    expect(req.factors).toHaveLength(1);
    expect(req.windows).toEqual([20]);
    expect(req.signals).toEqual([1.0]);
    expect('conjunction' in req).toBe(false);
  });

  it('builds a multi-factor perf request from a window_/signal_ row', () => {
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
    expect(req.factors).toHaveLength(2);
    expect(req.windows).toEqual([10, 14]);
    expect(req.signals).toEqual([0, 30]);
  });

  it('throws when a single-factor row is paired with a multi-factor config', () => {
    const cfg = baseCfg({
      factors: [
        baseCfg().factors[0],
        baseCfg().factors[0],
      ],
    });
    const row: Top10Row = { window: 10, signal: 1, sharpe: 1 };
    expect(() => buildPerformanceRequest(cfg, row)).toThrow();
  });
});
