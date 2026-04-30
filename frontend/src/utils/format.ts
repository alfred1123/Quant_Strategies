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

export function overfitColor(ratio: number | null): 'success' | 'warning' | 'error' | 'default' {
  if (ratio == null || isNaN(ratio)) return 'default';
  if (ratio < OVERFIT_THRESHOLDS.LOW) return 'success';
  if (ratio < OVERFIT_THRESHOLDS.HIGH) return 'warning';
  return 'error';
}

export function overfitLabel(ratio: number | null): string {
  if (ratio == null || isNaN(ratio)) return 'N/A';
  if (ratio < OVERFIT_THRESHOLDS.LOW) return 'Low Risk';
  if (ratio < OVERFIT_THRESHOLDS.HIGH) return 'Moderate';
  return 'High Risk';
}

export function formatMetric(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return 'N/A';
  return v.toFixed(4);
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
