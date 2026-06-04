import type { Top10Row, BacktestConfig } from '../types/backtest';
import { isSingleFactorRow, multiFactorParams } from './top10';

/**
 * Overfitting risk thresholds — single source of truth so color and label
 * never disagree. `ratio` is in [0, 1]:
 *   < LOW    → low risk    (green)
 *   < HIGH   → moderate    (amber)
 *   ≥ HIGH   → high risk   (red)
 */
export const OVERFIT_THRESHOLDS = { LOW: 0.3, HIGH: 0.5 } as const;

export function overfitColor(ratio: unknown): 'success' | 'warning' | 'error' | 'default' {
  const r = toFiniteNumber(ratio);
  if (r == null) return 'default';
  if (r < OVERFIT_THRESHOLDS.LOW) return 'success';
  if (r < OVERFIT_THRESHOLDS.HIGH) return 'warning';
  return 'error';
}

export function overfitLabel(ratio: unknown): string {
  const r = toFiniteNumber(ratio);
  if (r == null) return 'N/A';
  if (r < OVERFIT_THRESHOLDS.LOW) return 'Low Risk';
  if (r < OVERFIT_THRESHOLDS.HIGH) return 'Moderate';
  return 'High Risk';
}

/** Coerce API / REFDATA values (number, numeric string, Decimal-as-string) to a finite number. */
export function toFiniteNumber(v: unknown): number | null {
  if (v == null || v === '') return null;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

export function formatDecimal(v: unknown, digits = 4): string {
  const n = toFiniteNumber(v);
  if (n == null) return 'N/A';
  return n.toFixed(digits);
}

export function formatMetric(v: unknown): string {
  return formatDecimal(v, 4);
}

export function formatPercent(v: unknown, digits = 1): string {
  const n = toFiniteNumber(v);
  if (n == null) return 'N/A';
  return `${(n * 100).toFixed(digits)}%`;
}

export function rowLabel(row: Top10Row, cfg: BacktestConfig): string {
  if (cfg.factors.length <= 1) {
    if (isSingleFactorRow(row)) {
      return `window=${row.window}, signal=${row.signal}`;
    }
    // Single-mode config but the row is missing window/signal — display
    // dashes so the user sees a label rather than a generic 'unknown'.
    return 'window=-, signal=-';
  }
  const { windows, signals } = multiFactorParams(row);
  const parts: string[] = [];
  windows.forEach((w, i) => parts.push(`window_${i}=${w}`));
  signals.forEach((s, i) => parts.push(`signal_${i}=${s}`));
  return parts.length ? parts.join(', ') : 'unknown';
}
