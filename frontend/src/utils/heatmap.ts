import type { Top10Row } from '../types/backtest';
import { isSingleFactorRow } from './top10';

/** Build the windows × signals Sharpe matrix for the heatmap plot. */
export function buildHeatmapMatrix(grid: Top10Row[]): {
  windows: number[];
  signals: number[];
  z: (number | null)[][];
} {
  const singleRows = grid.filter(isSingleFactorRow);

  const windowsSet = new Set<number>();
  const signalsSet = new Set<number>();
  const sharpeByKey = new Map<string, number>();

  for (const row of singleRows) {
    windowsSet.add(row.window);
    signalsSet.add(row.signal);
    sharpeByKey.set(`${row.window}|${row.signal}`, row.sharpe);
  }

  const windows = [...windowsSet].sort((a, b) => a - b);
  const signals = [...signalsSet].sort((a, b) => a - b);
  const z = signals.map(sig =>
    windows.map(win => sharpeByKey.get(`${win}|${sig}`) ?? null),
  );

  return { windows, signals, z };
}
