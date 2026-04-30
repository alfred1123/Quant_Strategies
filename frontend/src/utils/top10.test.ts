import { describe, it, expect } from 'vitest';
import { isSingleFactorRow, readNumber, multiFactorParams } from './top10';
import type { Top10Row, MultiFactorRow } from '../types/backtest';

describe('isSingleFactorRow', () => {
  it('returns true when row has numeric window + signal', () => {
    const row: Top10Row = { window: 20, signal: 1.5, sharpe: 2 };
    expect(isSingleFactorRow(row)).toBe(true);
  });

  it('returns false when window/signal are missing', () => {
    const row: Top10Row = { sharpe: 1 };
    expect(isSingleFactorRow(row)).toBe(false);
  });

  it('returns false for multi-factor rows', () => {
    const row: Top10Row = { window_0: 10, signal_0: 0.5, sharpe: 1 };
    expect(isSingleFactorRow(row)).toBe(false);
  });
});

describe('readNumber', () => {
  it('returns the number when the key holds a finite number', () => {
    const row: Top10Row = { window: 20, sharpe: 1 };
    expect(readNumber(row, 'window')).toBe(20);
  });

  it('returns null when the key is missing', () => {
    const row: Top10Row = { sharpe: 1 };
    expect(readNumber(row, 'window_3')).toBeNull();
  });

  it('returns null for non-finite numbers (NaN, Infinity)', () => {
    const row: MultiFactorRow = { sharpe: 1, window_0: NaN };
    expect(readNumber(row, 'window_0')).toBeNull();
  });

  it('returns null for non-number values (string, null)', () => {
    const row = { sharpe: 1, label: 'foo', other: null } as unknown as MultiFactorRow;
    expect(readNumber(row, 'label')).toBeNull();
    expect(readNumber(row, 'other')).toBeNull();
  });
});

describe('multiFactorParams', () => {
  it('extracts windows + signals in factor order', () => {
    const row: MultiFactorRow = {
      window_0: 10, signal_0: 0.5,
      window_1: 20, signal_1: 1.0,
      sharpe: 2,
    };
    expect(multiFactorParams(row)).toEqual({ windows: [10, 20], signals: [0.5, 1.0] });
  });

  it('stops at the first missing factor index', () => {
    const row: MultiFactorRow = {
      window_0: 10, signal_0: 0.5,
      window_2: 30, signal_2: 1.5,  // gap at index 1 — these should be ignored
      sharpe: 2,
    };
    expect(multiFactorParams(row)).toEqual({ windows: [10], signals: [0.5] });
  });

  it('returns empty arrays when no factor params are present', () => {
    const row: MultiFactorRow = { sharpe: 1 };
    expect(multiFactorParams(row)).toEqual({ windows: [], signals: [] });
  });
});
