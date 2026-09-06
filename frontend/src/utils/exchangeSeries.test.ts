import { describe, expect, it } from 'vitest';
import type { BacktestConfig } from '../types/backtest';
import type { AppRow } from '../types/refdata';
import { exchangeSeriesKeys } from './exchangeSeries';

const apps: AppRow[] = [
  { app_id: 1, name: 'yahoo', display_name: 'Yahoo', class_name: 'YahooFinance', is_exchange_ind: 'N', description: null },
  { app_id: 34, name: 'bybit', display_name: 'Bybit', class_name: 'Bybit', is_exchange_ind: 'Y', description: null },
];

const base: BacktestConfig = {
  symbol: 'btcusdt.crypto',
  vendorSymbol: '',
  dataSource: 'bybit',
  start: '2020-03-25',
  end: '2026-09-06',
  assetType: 'Crypto',
  tmIntervalId: 2,
  tradingPeriod: 8760,
  feeBps: 10,
  conjunction: 'AND',
  factors: [{
    indicator: 'sma',
    strategy: 'momentum',
    data_column: 'price',
    window_range: { min: 5, max: 100, step: 5 },
    signal_range: { min: 0.25, max: 2.5, step: 0.25 },
  }],
  walkForward: false,
  splitRatio: 0.5,
  refreshDataset: false,
};

describe('exchangeSeriesKeys', () => {
  it('asks about the traded exchange series', () => {
    expect(exchangeSeriesKeys(base, apps)).toEqual([
      { internal_cusip: 'btcusdt.crypto', tm_interval_id: 2, source_app_id: 34 },
    ]);
  });

  it('includes a factor that reads a different product on the same venue', () => {
    const cfg: BacktestConfig = {
      ...base,
      factors: [{
        ...base.factors[0],
        symbol: 'ethusdt.crypto',
        data_source: 'bybit',
      }],
    };
    expect(exchangeSeriesKeys(cfg, apps).map(k => k.internal_cusip)).toEqual([
      'btcusdt.crypto',
      'ethusdt.crypto',
    ]);
  });

  it('does not ask a provider', () => {
    expect(exchangeSeriesKeys({ ...base, dataSource: 'yahoo' }, apps)).toEqual([]);
  });
});
