// UI form state
export interface RangeParam {
  min: number;
  max: number;
  step: number;
}

export interface FactorConfig {
  indicator: string;
  strategy: string;
  data_column: string;
  window_range: RangeParam;
  signal_range: RangeParam;
}

export interface BacktestConfig {
  symbol: string;
  start: string;
  end: string;
  assetType: string;
  tradingPeriod: number;
  feeBps: number;
  mode: 'single' | 'multi';
  // single-factor
  indicator: string;
  strategy: string;
  windowRange: RangeParam;
  signalRange: RangeParam;
  // multi-factor
  conjunction: string;
  factors: FactorConfig[];
  // walk-forward
  walkForward: boolean;
  splitRatio: number;
}

// API types (snake_case matches backend Pydantic models)
export interface OptimizeRequest {
  symbol: string;
  start: string;
  end: string;
  mode: 'single' | 'multi';
  trading_period: number;
  fee_bps: number;
  data_source?: string;
  indicator?: string;
  strategy?: string;
  window_range?: RangeParam;
  signal_range?: RangeParam;
  conjunction?: string;
  factors?: FactorConfig[];
}

export interface PerformanceRequest {
  symbol: string;
  start: string;
  end: string;
  mode: 'single' | 'multi';
  trading_period: number;
  fee_bps: number;
  data_source?: string;
  indicator?: string;
  strategy?: string;
  window?: number;
  signal?: number;
  conjunction?: string;
  factors?: FactorConfig[];
  windows?: number[];
  signals?: number[];
}

export interface Top10Row {
  window?: number;
  signal?: number;
  sharpe: number;
  [key: string]: unknown;
}

export interface OptimizeResponse {
  total_trials: number;
  valid: number;
  best: Top10Row;
  top10: Top10Row[];
  grid: Top10Row[];
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
