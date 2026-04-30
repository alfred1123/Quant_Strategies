import { describe, it, expect } from 'vitest';
import { validateBacktestConfig, firstValidationError } from './validate';
import type { BacktestConfig } from '../types/backtest';

const baseCfg: BacktestConfig = {
  symbol: 'btcusdt.crypto',
  vendorSymbol: '',
  dataSource: 'yahoo',
  start: '2020-01-01',
  end: '2024-01-01',
  assetType: 'Crypto',
  tradingPeriod: 365,
  feeBps: 5,
  mode: 'single',
  indicator: '',
  strategy: '',
  windowRange: { min: 5, max: 100, step: 5 },
  signalRange: { min: 0.25, max: 2.5, step: 0.25 },
  conjunction: 'AND',
  factors: [
    {
      indicator: 'sma',
      strategy: 'momentum',
      data_column: 'price',
      window_range: { min: 5, max: 100, step: 5 },
      signal_range: { min: 0.25, max: 2.5, step: 0.25 },
    },
  ],
  walkForward: false,
  splitRatio: 0.5,
  refreshDataset: false,
};

describe('validateBacktestConfig', () => {
  it('returns no errors for a fully populated config', () => {
    expect(validateBacktestConfig(baseCfg)).toEqual([]);
  });

  it('flags missing product (both symbol and vendorSymbol empty)', () => {
    const cfg = { ...baseCfg, symbol: '', vendorSymbol: '' };
    expect(validateBacktestConfig(cfg)).toContain('Product or Vendor Symbol');
  });

  it('accepts vendorSymbol alone (no internal symbol)', () => {
    const cfg = { ...baseCfg, symbol: '', vendorSymbol: 'BTC-USD' };
    expect(validateBacktestConfig(cfg)).not.toContain('Product or Vendor Symbol');
  });

  it('flags missing assetType', () => {
    const cfg = { ...baseCfg, assetType: '' };
    expect(validateBacktestConfig(cfg)).toContain('Asset Type');
  });

  it('flags missing indicator/strategy without factor index when single factor', () => {
    const cfg = {
      ...baseCfg,
      factors: [{ ...baseCfg.factors[0], indicator: '', strategy: '' }],
    };
    const missing = validateBacktestConfig(cfg);
    expect(missing).toContain('Indicator');
    expect(missing).toContain('Strategy');
  });

  it('prefixes factor index when there are multiple factors', () => {
    const cfg: BacktestConfig = {
      ...baseCfg,
      factors: [
        { ...baseCfg.factors[0], indicator: '' },
        { ...baseCfg.factors[0], strategy: '' },
      ],
    };
    const missing = validateBacktestConfig(cfg);
    expect(missing).toContain('Factor 1 Indicator');
    expect(missing).toContain('Factor 2 Strategy');
  });

  it('flags zero-factor config', () => {
    const cfg = { ...baseCfg, factors: [] };
    expect(validateBacktestConfig(cfg)).toContain('At least one Factor');
  });
});

describe('firstValidationError', () => {
  it('returns null for valid config', () => {
    expect(firstValidationError(baseCfg)).toBeNull();
  });

  it('returns a single human-readable error string when invalid', () => {
    const cfg = { ...baseCfg, assetType: '' };
    const err = firstValidationError(cfg);
    expect(err).toMatch(/Cannot run/);
    expect(err).toContain('Asset Type');
  });
});
