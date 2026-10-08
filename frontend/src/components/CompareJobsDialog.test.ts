import { describe, expect, it } from 'vitest';
import { extractJobSummary, formatDiff } from './CompareJobsDialog';
import type { JobDetail } from '../types/jobs';

function detail(
  config: Record<string, unknown>,
  metrics: Record<string, unknown> = {},
): JobDetail {
  return {
    strategy_nm: 'sma',
    config_json: config,
    result: { performance: { strategy_metrics: metrics } },
  } as JobDetail;
}

describe('formatDiff', () => {
  it('paints a larger max-drawdown diff red and a smaller one green', () => {
    expect(formatDiff(0.4, 0.2, true, true)).toEqual({ text: '+20.00 pp', color: 'error.main' });
    expect(formatDiff(0.2, 0.4, true, true)).toEqual({ text: '-20.00 pp', color: 'success.main' });
  });

  it('keeps Sharpe, Calmar, and Return higher-is-better', () => {
    expect(formatDiff(1.5, 1.0).color).toBe('success.main');
    expect(formatDiff(1.0, 1.5).color).toBe('error.main');
    expect(formatDiff(2.0, 1.0).color).toBe('success.main');
    expect(formatDiff(0.5, 0.2, true).color).toBe('success.main');
    expect(formatDiff(0.2, 0.5, true).color).toBe('error.main');
  });

  it('treats a zero diff and a missing value as neutral', () => {
    expect(formatDiff(0.2, 0.2, true, true)).toEqual({ text: '0', color: 'text.secondary' });
    expect(formatDiff(null, 0.2, true, true)).toEqual({ text: '—', color: 'text.secondary' });
    expect(formatDiff(0.2, null)).toEqual({ text: '—', color: 'text.secondary' });
  });
});

describe('extractJobSummary', () => {
  it('shows window_range and signal_range min, max, and step', () => {
    const summary = extractJobSummary(detail({
      factors: [{
        indicator: 'bollinger',
        window: 20,
        signal: 1.5,
        window_range: { min: 5, max: 100, step: 5 },
        signal_range: { min: 0, max: 2.5, step: 0.25 },
      }],
    }));
    expect(summary.factors).toEqual([{
      name: 'bollinger',
      window: 'min 5 max 100 step 5',
      signal: 'min 0 max 2.5 step 0.25',
    }]);
  });

  it('does not show a bare window or signal number', () => {
    const summary = extractJobSummary(detail({
      factors: [{ indicator: 'sma', window: 20, signal: 1 }],
    }));
    expect(summary.factors).toEqual([{ name: 'sma', window: undefined, signal: undefined }]);
  });

  it('drops a range that is missing min, max, or step', () => {
    const summary = extractJobSummary(detail({
      factors: [{ indicator: 'rsi', window_range: { min: 5, max: 20 }, signal_range: null }],
    }));
    expect(summary.factors[0].window).toBeUndefined();
    expect(summary.factors[0].signal).toBeUndefined();
  });

  it('shows the raw start and end strings and ignores the old date keys', () => {
    const summary = extractJobSummary(detail({
      start: '2020-01-01',
      end: '2024-12-31',
      start_date: '1999-01-01',
      startDate: '1998-06-15',
      end_date: '1999-12-31',
      endDate: '1998-12-31',
    }));
    expect(summary.dateRange).toBe('2020-01-01 → 2024-12-31');
  });

  it('ignores start_date and startDate when start and end are absent', () => {
    const summary = extractJobSummary(detail({
      start_date: '1999-01-01',
      startDate: '1998-06-15',
      end_date: '1999-12-31',
      endDate: '1998-12-31',
    }));
    expect(summary.dateRange).toBeNull();
  });

  it('returns no date range and no factors for an empty config', () => {
    const summary = extractJobSummary(detail({}));
    expect(summary.dateRange).toBeNull();
    expect(summary.factors).toEqual([]);
    expect(summary.maxDrawdown).toBeNull();
  });
});
