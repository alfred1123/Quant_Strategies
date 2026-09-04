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
  dataSource: 'yahoo',
  assetType: 'crypto',
  tmIntervalId: 1,
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
  it('includes trade product, its venue, its cadence, and factor metric', () => {
    expect(buildStrategyNm(baseConfig(), 'DAILY')).toBe(
      'btcusdt.crypto@yahoo:DAILY ← btcusdt.crypto/get_bollinger_band/momentum_band_signal on c',
    );
  });

  it('separates cross-product factor sources', () => {
    const cfg = baseConfig({
      symbol: 'ethusdt.crypto',
      factors: [
        baseFactor({ symbol: 'vix.equity_us', indicator: 'get_rsi', strategy: 'momentum_band_signal' }),
      ],
    });
    expect(buildStrategyNm(cfg, 'DAILY')).toBe(
      'ethusdt.crypto@yahoo:DAILY ← vix.equity_us/get_rsi/momentum_band_signal on c',
    );
  });

  it('treats the same recipe on two venues as two strategies', () => {
    const onYahoo = buildStrategyNm(baseConfig({ dataSource: 'yahoo' }), 'DAILY');
    const onBybit = buildStrategyNm(baseConfig({ dataSource: 'bybit' }), 'DAILY');
    expect(onYahoo).not.toBe(onBybit);
  });

  it('treats the same recipe on two cadences as two strategies', () => {
    // The failure this guards: an hourly run of a daily recipe became v3 of
    // the daily lineage, where promotion would compare a Sharpe annualised
    // over 8760 periods against one annualised over 365.
    const daily = buildStrategyNm(baseConfig({ dataSource: 'bybit' }), 'DAILY');
    const hourly = buildStrategyNm(baseConfig({ dataSource: 'bybit' }), '1H');
    expect(daily).not.toBe(hourly);
    expect(hourly).toContain('btcusdt.crypto@bybit:1H ←');
  });

  it('names the traded venue even when a factor reads from another', () => {
    // The failure this guards: the name said "on bybit:price" because a
    // factor was set to Bybit, while the traded series stayed on Yahoo.
    const cfg = baseConfig({
      dataSource: 'yahoo',
      factors: [baseFactor({ data_source: 'bybit', data_column: 'price' })],
    });
    const nm = buildStrategyNm(cfg, 'DAILY');
    expect(nm).toContain('btcusdt.crypto@yahoo:DAILY ←');
    expect(nm).toContain('on bybit:price');
  });

  it('treats different metrics as distinct strategies', () => {
    const price = buildStrategyNm(baseConfig(), 'DAILY');
    const volume = buildStrategyNm(
      baseConfig({ factors: [baseFactor({ data_column: 'v' })] }), 'DAILY',
    );
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
    expect(buildStrategyNm(cfg, 'DAILY')).toContain(' AND ');
    expect(buildStrategyNm(cfg, 'DAILY').split(' AND ')).toHaveLength(2);
  });

  it('prefers vendor_symbol over symbol for factor source', () => {
    const cfg = baseConfig({
      factors: [baseFactor({ symbol: 'vix.equity_us', vendor_symbol: '^VIX' })],
    });
    expect(buildStrategyNm(cfg, 'DAILY')).toContain('^VIX/get_bollinger_band/');
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
