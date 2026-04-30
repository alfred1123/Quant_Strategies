import { describe, it, expect } from 'vitest';
import { buildHeatmapMatrix } from './HeatmapChart';
import type { Top10Row } from '../types/backtest';

describe('buildHeatmapMatrix', () => {
  it('returns empty axes for an empty grid', () => {
    expect(buildHeatmapMatrix([])).toEqual({ windows: [], signals: [], z: [] });
  });

  it('extracts unique sorted windows + signals from single-factor rows', () => {
    const grid: Top10Row[] = [
      { window: 20, signal: 1.0, sharpe: 1.5 },
      { window: 10, signal: 0.5, sharpe: 0.5 },
      { window: 20, signal: 0.5, sharpe: 1.0 },
      { window: 10, signal: 1.0, sharpe: 0.7 },
    ];
    const m = buildHeatmapMatrix(grid);
    expect(m.windows).toEqual([10, 20]);
    expect(m.signals).toEqual([0.5, 1.0]);
    // z is signals × windows. signal=0.5 row first.
    expect(m.z).toEqual([
      [0.5, 1.0],
      [0.7, 1.5],
    ]);
  });

  it('returns null for cells missing in the grid', () => {
    const grid: Top10Row[] = [
      { window: 10, signal: 0.5, sharpe: 0.5 },
      { window: 20, signal: 1.0, sharpe: 1.5 },
    ];
    const m = buildHeatmapMatrix(grid);
    // Off-diagonal cells were never observed → null.
    expect(m.z).toEqual([
      [0.5, null],
      [null, 1.5],
    ]);
  });

  it('ignores multi-factor rows in the grid', () => {
    const grid: Top10Row[] = [
      { window: 10, signal: 0.5, sharpe: 1 },
      { window_0: 10, signal_0: 0.5, sharpe: 2 },  // multi-factor — skipped
    ];
    const m = buildHeatmapMatrix(grid);
    expect(m.windows).toEqual([10]);
    expect(m.signals).toEqual([0.5]);
    expect(m.z).toEqual([[1]]);
  });
});
