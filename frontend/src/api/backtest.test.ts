import { describe, it, expect, vi, beforeEach } from 'vitest';
import { runOptimize, runPerformance, runWalkForward } from './backtest';
import { apiClient } from './client';

vi.mock('./client', () => ({
  apiClient: {
    post: vi.fn(),
    defaults: { baseURL: '/api/v1' },
  },
}));

const mockedPost = vi.mocked(apiClient.post);

beforeEach(() => vi.clearAllMocks());

const FACTOR = {
  indicator: 'sma',
  strategy: 'momentum',
  data_column: 'price',
  window_range: { min: 5, max: 100, step: 5 },
  signal_range: { min: 0.25, max: 2.5, step: 0.25 },
};

describe('runOptimize', () => {
  it('posts to /backtest/optimize and returns data', async () => {
    const expected = { total_trials: 100, valid: 80, best: {}, top10: [], grid: [] };
    mockedPost.mockResolvedValue({ data: expected });

    const result = await runOptimize({
      symbol: 'BTC-USD', start: '2020-01-01', end: '2024-01-01',
      trading_period: 365, fee_bps: 5, data_source: 'yahoo', tm_interval_id: 1, factors: [FACTOR],
    });

    expect(mockedPost).toHaveBeenCalledWith('/backtest/optimize', expect.objectContaining({ symbol: 'BTC-USD' }));
    expect(result).toEqual(expected);
  });
});

describe('runPerformance', () => {
  it('posts to /backtest/performance', async () => {
    const expected = { strategy_metrics: {}, buy_hold_metrics: {}, equity_curve: [], perf_csv: '' };
    mockedPost.mockResolvedValue({ data: expected });

    const result = await runPerformance({
      symbol: 'AAPL', start: '2020-01-01', end: '2024-01-01',
      trading_period: 252, fee_bps: 5, data_source: 'yahoo', tm_interval_id: 1,
      factors: [FACTOR], windows: [20], signals: [1],
    });

    expect(mockedPost).toHaveBeenCalledWith('/backtest/performance', expect.objectContaining({ symbol: 'AAPL' }));
    expect(result).toEqual(expected);
  });
});

describe('runWalkForward', () => {
  it('posts to /backtest/walk-forward', async () => {
    const expected = { best_window: 20, best_signal: 1, is_metrics: {}, oos_metrics: {}, overfitting_ratio: 0.3, equity_curve: [], split_date: '2022-01-01' };
    mockedPost.mockResolvedValue({ data: expected });

    const result = await runWalkForward({
      symbol: 'BTC-USD', start: '2020-01-01', end: '2024-01-01',
      trading_period: 365, fee_bps: 5, split_ratio: 0.5, data_source: 'yahoo', tm_interval_id: 1,
      factors: [FACTOR],
    });

    expect(mockedPost).toHaveBeenCalledWith('/backtest/walk-forward', expect.objectContaining({ symbol: 'BTC-USD' }));
    expect(result).toEqual(expected);
  });
});
