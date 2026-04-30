import { describe, it, expect, vi, beforeEach } from 'vitest';
import { runOptimize, runOptimizeStream, runPerformance, runWalkForward } from './backtest';
import { apiClient } from './client';

vi.mock('./client', () => ({
  apiClient: {
    post: vi.fn(),
    defaults: { baseURL: '/api/v1' },
  },
}));

const mockedPost = vi.mocked(apiClient.post);

beforeEach(() => vi.clearAllMocks());

describe('runOptimize', () => {
  it('posts to /backtest/optimize and returns data', async () => {
    const expected = { total_trials: 100, valid: 80, best: {}, top10: [], grid: [] };
    mockedPost.mockResolvedValue({ data: expected });

    const result = await runOptimize({ symbol: 'BTC-USD', start: '2020-01-01', end: '2024-01-01', mode: 'single', trading_period: 365, fee_bps: 5 });

    expect(mockedPost).toHaveBeenCalledWith('/backtest/optimize', expect.objectContaining({ symbol: 'BTC-USD' }));
    expect(result).toEqual(expected);
  });
});

describe('runPerformance', () => {
  it('posts to /backtest/performance', async () => {
    const expected = { strategy_metrics: {}, buy_hold_metrics: {}, equity_curve: [], perf_csv: '' };
    mockedPost.mockResolvedValue({ data: expected });

    const result = await runPerformance({ symbol: 'AAPL', start: '2020-01-01', end: '2024-01-01', mode: 'single', trading_period: 252, fee_bps: 5, window: 20, signal: 1 });

    expect(mockedPost).toHaveBeenCalledWith('/backtest/performance', expect.objectContaining({ symbol: 'AAPL' }));
    expect(result).toEqual(expected);
  });
});

describe('runWalkForward', () => {
  it('posts to /backtest/walk-forward', async () => {
    const expected = { best_window: 20, best_signal: 1, is_metrics: {}, oos_metrics: {}, overfitting_ratio: 0.3, equity_curve: [], split_date: '2022-01-01' };
    mockedPost.mockResolvedValue({ data: expected });

    const result = await runWalkForward({ symbol: 'BTC-USD', start: '2020-01-01', end: '2024-01-01', mode: 'single', trading_period: 365, fee_bps: 5, split_ratio: 0.5 });

    expect(mockedPost).toHaveBeenCalledWith('/backtest/walk-forward', expect.objectContaining({ symbol: 'BTC-USD' }));
    expect(result).toEqual(expected);
  });
});

describe('runOptimizeStream', () => {
  function makeSseChunk(event: string, data: unknown) {
    return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  }

  it('resolves with the result event after progress events', async () => {
    const progress = { trial: 1, total: 10, best_sharpe: 1.5 };
    const result = { total_trials: 10, valid: 8, best: { sharpe: 2 }, top10: [], grid: [] };

    const chunks = [
      makeSseChunk('init', { trial: 0, total: 10, best_sharpe: null }),
      makeSseChunk('progress', progress),
      makeSseChunk('result', result),
    ];

    const stream = new ReadableStream({
      start(controller) {
        for (const chunk of chunks) {
          controller.enqueue(new TextEncoder().encode(chunk));
        }
        controller.close();
      },
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: stream,
    }));

    const onProgress = vi.fn();
    const res = await runOptimizeStream(
      { symbol: 'BTC-USD', start: '2020-01-01', end: '2024-01-01', mode: 'single', trading_period: 365, fee_bps: 5 },
      onProgress,
    );

    expect(onProgress).toHaveBeenCalledTimes(2);
    expect(res).toEqual(result);

    vi.unstubAllGlobals();
  });

  it('rejects on error event', async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(makeSseChunk('error', { detail: 'boom' })));
        controller.close();
      },
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: stream }));

    await expect(
      runOptimizeStream(
        { symbol: 'X', start: '', end: '', mode: 'single', trading_period: 365, fee_bps: 0 },
        vi.fn(),
      ),
    ).rejects.toThrow('boom');

    vi.unstubAllGlobals();
  });

  it('rejects on non-ok HTTP response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: () => Promise.resolve({ detail: 'Validation error' }),
    }));

    await expect(
      runOptimizeStream(
        { symbol: 'X', start: '', end: '', mode: 'single', trading_period: 365, fee_bps: 0 },
        vi.fn(),
      ),
    ).rejects.toThrow('Validation error');

    vi.unstubAllGlobals();
  });
});
