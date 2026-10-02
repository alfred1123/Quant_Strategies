export interface BacktestSearchRow {
  backtest_search_id: number;
  trial_budget: number;
  seed: number;
  max_attempts_factor: number;
  over_budget_mode: string;
}

export interface PromotionMetricRow {
  promotion_metric_id: number;
  name: string;
  display_name: string;
  metric_key: string;
  direction: 'higher_is_better' | 'lower_is_better';
  requirement_type: 'HARD' | 'SOFT';
  priority: number;
  threshold: number | string | null;
  description: string | null;
}
