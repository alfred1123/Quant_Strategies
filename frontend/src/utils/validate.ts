import type { BacktestConfig } from '../types/backtest';

/**
 * Single source of truth for backtest config validation.
 * Returns a list of human-readable missing-field labels (empty when valid).
 *
 * Used by both `ConfigDrawer` (to enable/disable Run + show inline missing list)
 * and `BacktestPage` (to short-circuit `handleRun`). Keep them in sync — if
 * you add a new required field, only edit this file.
 */
export function validateBacktestConfig(cfg: BacktestConfig): string[] {
  const missing: string[] = [];

  if (!cfg.symbol.trim() && !cfg.vendorSymbol.trim()) {
    missing.push('Product or Vendor Symbol');
  }
  if (!cfg.assetType) {
    missing.push('Asset Type');
  }
  if (cfg.factors.length === 0) {
    missing.push('At least one Factor');
  }
  cfg.factors.forEach((f, i) => {
    const prefix = cfg.factors.length > 1 ? `Factor ${i + 1} ` : '';
    if (!f.indicator) missing.push(`${prefix}Indicator`);
    if (!f.strategy) missing.push(`${prefix}Strategy`);
  });

  return missing;
}

/** Convenience: turn the missing list into a single error message. */
export function firstValidationError(cfg: BacktestConfig): string | null {
  const missing = validateBacktestConfig(cfg);
  if (missing.length === 0) return null;
  return `Cannot run — missing: ${missing.join(', ')}`;
}
