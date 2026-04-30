// ─────────────────────────────────────────────────────────────────────────
// Form state types
// ─────────────────────────────────────────────────────────────────────────

export interface RangeParam {
  min: number;
  max: number;
  step: number;
}

/** Cross-product factor (used in mode='multi'). */
export interface FactorConfig {
  // ── factor-only ──
  indicator: string;
  strategy: string;
  data_column: string;
  window_range: RangeParam;
  signal_range: RangeParam;
  symbol?: string;         // internal_cusip for cross-product factor (pair trade)
  vendor_symbol?: string;  // direct vendor symbol override for this factor
  data_source?: string;    // per-factor data source override
}

/** Top-level backtest form. */
export interface BacktestConfig {
  // ── trading product (product-only) ──
  symbol: string;       // internal_cusip from product dropdown
  vendorSymbol: string; // direct vendor symbol override (e.g. BTC-USD)
  dataSource: string;
  assetType: string;

  // ── shared controls (apply to product + every factor) ──
  start: string;
  end: string;
  tradingPeriod: number;
  feeBps: number;
  /** When true, refetch all product+factor data from the provider and
   *  insert a new BT.API_REQUEST version. When false (default), serve
   *  from cache only — backend returns 400 if the cache misses. */
  refreshDataset: boolean;

  // ── single-factor mode ──
  mode: 'single' | 'multi';
  indicator: string;
  strategy: string;
  windowRange: RangeParam;
  signalRange: RangeParam;

  // ── multi-factor mode ──
  conjunction: string;
  factors: FactorConfig[];

  // ── walk-forward (analysis option) ──
  walkForward: boolean;
  splitRatio: number;
}

// ─────────────────────────────────────────────────────────────────────────
// API request types (snake_case to match backend Pydantic models)
// ─────────────────────────────────────────────────────────────────────────

export interface OptimizeRequest {
  // ── trading product ──
  symbol: string;
  data_source?: string;

  // ── shared (product + factors) ──
  start: string;
  end: string;
  trading_period: number;
  fee_bps: number;
  refresh_dataset?: boolean;

  // ── strategy/mode ──
  mode: 'single' | 'multi';

  // ── single-factor ──
  indicator?: string;
  strategy?: string;
  window_range?: RangeParam;
  signal_range?: RangeParam;

  // ── multi-factor ──
  conjunction?: string;
  factors?: FactorConfig[];

  // ── walk-forward (run inline when true) ──
  walk_forward?: boolean;
  split_ratio?: number;
}

export interface PerformanceRequest {
  // ── trading product ──
  symbol: string;
  data_source?: string;

  // ── shared ──
  start: string;
  end: string;
  trading_period: number;
  fee_bps: number;
  refresh_dataset?: boolean;

  // ── strategy/mode ──
  mode: 'single' | 'multi';

  // ── single-factor ──
  indicator?: string;
  strategy?: string;
  window?: number;
  signal?: number;

  // ── multi-factor ──
  conjunction?: string;
  factors?: FactorConfig[];
  windows?: number[];
  signals?: number[];
}

/**
 * One row of optimization results. Discriminated by the presence of
 * `window`/`signal` (single-factor) vs `window_0`/`signal_0`/... (multi-factor).
 *
 * Use the helpers in `utils/top10.ts` (`isSingleFactorRow`, `multiFactorParams`)
 * to read window/signal values safely instead of `as number` casts.
 */
export type Top10Row = SingleFactorRow | MultiFactorRow;

export interface SingleFactorRow {
  window: number;
  signal: number;
  sharpe: number;
  /** Reserved for future per-row metadata; not used for window/signal lookups. */
  [key: string]: number | string | null | undefined;
}

export interface MultiFactorRow {
  sharpe: number;
  /**
   * Per-factor params live under `window_0`, `signal_0`, `window_1`, `signal_1`, ...
   * Keep the index signature wide enough to allow that, but narrow values to numbers.
   */
  [key: string]: number | string | null | undefined;
}

export interface OptimizeResponse {
  total_trials: number;
  valid: number;
  best: Top10Row;
  top10: Top10Row[];
  grid: Top10Row[];
  performance?: PerformanceResponse;
  walk_forward?: WalkForwardResponse;
}

export interface OptimizeProgress {
  trial: number;
  total: number;
  best_sharpe: number | null;
}

export interface EquityPoint {
  datetime: string;
  cumu: number;
  buy_hold_cumu: number;
  dd: number;
  buy_hold_dd: number;
}

export interface PerformanceResponse {
  strategy_metrics: Record<string, number>;
  buy_hold_metrics: Record<string, number>;
  equity_curve: EquityPoint[];
  perf_csv: string;
}

// Walk-forward analysis
export interface WalkForwardRequest extends OptimizeRequest {
  split_ratio: number;
}

export interface WalkForwardResponse {
  best_window: number | number[];
  best_signal: number | number[];
  is_metrics: Record<string, number>;
  oos_metrics: Record<string, number>;
  overfitting_ratio: number | null;
  equity_curve: EquityPoint[];
  split_date: string;
}
