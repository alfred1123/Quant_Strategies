import { describe, it, expect } from 'vitest';
import { overfitColor, overfitLabel, formatMetric, rowLabel } from './format';
import type { BacktestConfig, Top10Row } from '../types/backtest';

describe('overfitColor', () => {
  it('returns default for null/NaN', () => {
    expect(overfitColor(null)).toBe('default');
    expect(overfitColor(NaN)).toBe('default');
  });
  it('returns success for low ratio', () => {
    expect(overfitColor(0.1)).toBe('success');
    expect(overfitColor(0.29)).toBe('success');
  });
  it('returns warning for moderate ratio', () => {
    expect(overfitColor(0.3)).toBe('warning');
    expect(overfitColor(0.49)).toBe('warning');
  });
  it('returns error for high ratio', () => {
    expect(overfitColor(0.5)).toBe('error');
    expect(overfitColor(0.9)).toBe('error');
  });
});

describe('overfitLabel', () => {
  // Thresholds (LOW=0.3, HIGH=0.5) intentionally match overfitColor so the
  // displayed color and label can never disagree. See OVERFIT_THRESHOLDS in
  // src/utils/format.ts.
  it('returns N/A for null/NaN', () => {
    expect(overfitLabel(null)).toBe('N/A');
    expect(overfitLabel(NaN)).toBe('N/A');
  });
  it('returns Low Risk below 0.3', () => {
    expect(overfitLabel(0.2)).toBe('Low Risk');
    expect(overfitLabel(0.29)).toBe('Low Risk');
  });
  it('returns Moderate for 0.3–0.49', () => {
    expect(overfitLabel(0.3)).toBe('Moderate');
    expect(overfitLabel(0.49)).toBe('Moderate');
  });
  it('returns High Risk at 0.5+', () => {
    expect(overfitLabel(0.5)).toBe('High Risk');
    expect(overfitLabel(0.7)).toBe('High Risk');
    expect(overfitLabel(1.0)).toBe('High Risk');
  });
});

describe('formatMetric', () => {
  it('returns N/A for null/undefined/NaN', () => {
    expect(formatMetric(null)).toBe('N/A');
    expect(formatMetric(undefined)).toBe('N/A');
    expect(formatMetric(NaN)).toBe('N/A');
  });
  it('formats to 4 decimal places', () => {
    expect(formatMetric(1.23456789)).toBe('1.2346');
    expect(formatMetric(0)).toBe('0.0000');
  });
});

describe('rowLabel', () => {
  const singleCfg = { factors: [{ indicator: 'sma' }] } as unknown as BacktestConfig;
  const multiCfg = { factors: [{}, {}] } as unknown as BacktestConfig;

  it('formats single-factor row', () => {
    const row: Top10Row = { window: 20, signal: 1.5, sharpe: 2.0 };
    expect(rowLabel(row, singleCfg)).toBe('window=20, signal=1.5');
  });

  it('handles missing window/signal in single mode', () => {
    const row: Top10Row = { sharpe: 1.0 };
    expect(rowLabel(row, singleCfg)).toBe('window=-, signal=-');
  });

  it('formats multi-factor row with window_/signal_ keys', () => {
    const row: Top10Row = { window_0: 10, signal_0: 0.5, window_1: 20, signal_1: 1.0, sharpe: 2 };
    const label = rowLabel(row, multiCfg);
    expect(label).toContain('window_0=10');
    expect(label).toContain('signal_0=0.5');
    expect(label).toContain('window_1=20');
    expect(label).toContain('signal_1=1');
  });
});
