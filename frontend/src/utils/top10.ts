import type { Top10Row, SingleFactorRow, MultiFactorRow } from '../types/backtest';

/**
 * Single-factor rows always carry plain `window` + `signal` numbers.
 * Multi-factor rows carry `window_0`, `signal_0`, `window_1`, ... instead.
 */
export function isSingleFactorRow(row: Top10Row): row is SingleFactorRow {
  return typeof (row as SingleFactorRow).window === 'number'
    && typeof (row as SingleFactorRow).signal === 'number';
}

/**
 * Read a numeric value from a row by key. Returns `null` if the key is
 * missing or the value isn't a finite number — never throws or coerces.
 */
export function readNumber(row: Top10Row, key: string): number | null {
  const v = (row as Record<string, unknown>)[key];
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/**
 * Pull `window_0`, `signal_0`, `window_1`, ... from a multi-factor row in
 * factor order. Stops at the first missing factor index.
 */
export function multiFactorParams(row: MultiFactorRow): { windows: number[]; signals: number[] } {
  const windows: number[] = [];
  const signals: number[] = [];
  for (let i = 0; ; i++) {
    const w = readNumber(row, `window_${i}`);
    const s = readNumber(row, `signal_${i}`);
    if (w === null || s === null) break;
    windows.push(w);
    signals.push(s);
  }
  return { windows, signals };
}
