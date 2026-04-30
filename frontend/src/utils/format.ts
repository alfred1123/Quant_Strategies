import type { Top10Row, BacktestConfig } from '../types/backtest';

export function overfitColor(ratio: number | null): 'success' | 'warning' | 'error' | 'default' {
  if (ratio == null || isNaN(ratio)) return 'default';
  if (ratio < 0.3) return 'success';
  if (ratio < 0.5) return 'warning';
  return 'error';
}

export function overfitLabel(ratio: number | null): string {
  if (ratio == null || isNaN(ratio)) return 'N/A';
  if (ratio < 0.3) return 'Low Risk';
  if (ratio < 0.7) return 'Moderate';
  return 'High Risk';
}

export function formatMetric(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return 'N/A';
  return v.toFixed(4);
}

export function rowLabel(row: Top10Row, cfg: BacktestConfig): string {
  if (cfg.factors.length <= 1) return `window=${row.window ?? '-'}, signal=${row.signal ?? '-'}`;
  return Object.keys(row)
    .filter(k => k.startsWith('window_') || k.startsWith('signal_'))
    .map(k => `${k}=${row[k]}`)
    .join(', ');
}
