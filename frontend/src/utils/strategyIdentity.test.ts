import { describe, expect, it } from 'vitest';
import type { BacktestConfig, FactorConfig } from '../types/backtest';
import { buildStrategyNm, strategyGroupKey } from './strategyIdentity';

const baseFactor = (overrides: Partial<FactorConfig> = {}): FactorConfig => ({
  data_column: 'c',
  indicator: 'get_bollinger_band',
  strategy: 'momentum_band_signal',
  window_range: { min: 10, max: 20, step: 1 },
  signal_range: { min: 1, max: 2, step: 0.1 },
  ...overrides,
});

const baseConfig = (overrides: Partial<BacktestConfig> = {}): BacktestConfig => ({
  symbol: 'btcusdt.crypto',
  vendorSymbol: '',
  dataSource: '',
  assetType: 'crypto',
  start: '2020-01-01',
  end: '2024-01-01',
  tradingPeriod: 1,
  feeBps: 0,
  refreshDataset: false,
  conjunction: 'AND',
  factors: [baseFactor()],
  walkForward: false,
  splitRatio: 0.7,
  ...overrides,
});

describe('buildStrategyNm', () => {
  it('includes trade product and factor metric', () => {
    expect(buildStrategyNm(baseConfig())).toBe(
      'btcusdt.crypto ← btcusdt.crypto/get_bollinger_band/momentum_band_signal on c',
    );
  });

  it('separates cross-product factor sources', () => {
    const cfg = baseConfig({
      symbol: 'ethusdt.crypto',
      factors: [
        baseFactor({ symbol: 'vix.equity_us', indicator: 'get_rsi', strategy: 'momentum_band_signal' }),
      ],
    });
    expect(buildStrategyNm(cfg)).toBe(
      'ethusdt.crypto ← vix.equity_us/get_rsi/momentum_band_signal on c',
    );
  });

  it('treats different metrics as distinct strategies', () => {
    const price = buildStrategyNm(baseConfig());
    const volume = buildStrategyNm(baseConfig({ factors: [baseFactor({ data_column: 'v' })] }));
    expect(price).not.toBe(volume);
    expect(volume).toContain(' on v');
  });

  it('joins multi-factor configs with conjunction', () => {
    const cfg = baseConfig({
      factors: [
        baseFactor(),
        baseFactor({ indicator: 'get_rsi', strategy: 'reversion_band_signal' }),
      ],
    });
    expect(buildStrategyNm(cfg)).toContain(' AND ');
    expect(buildStrategyNm(cfg).split(' AND ')).toHaveLength(2);
  });

  it('prefers vendor_symbol over symbol for factor source', () => {
    const cfg = baseConfig({
      factors: [baseFactor({ symbol: 'vix.equity_us', vendor_symbol: '^VIX' })],
    });
    expect(buildStrategyNm(cfg)).toContain('^VIX/get_bollinger_band/');
  });
});

describe('strategyGroupKey', () => {
  it('combines user and name', () => {
    expect(strategyGroupKey('alice', 'foo ← bar', 'uuid')).toBe('alice\0foo ← bar');
  });

  it('falls back to strategy id when name is null', () => {
    expect(strategyGroupKey('alice', null, 'uuid-123')).toBe('alice\0uuid-123');
  });
});
