// Mirrors api/schemas/promotion.py — keep in sync.

export interface GateResult {
  name: string;
  passed: boolean;
  value: number | string | null;
  threshold: number | string | null;
}

export interface PromotionRow {
  promotion_id: string;
  queue_id: string;
  strategy_id: string;
  strategy_vid: number;
  strategy_nm: string | null;
  is_best_ind: string | null;
  outcome: string;
  compared_vid: number | null;
  gate_results: GateResult[] | null;
  sharpe_ratio: number | string | null;
  calmar_ratio: number | string | null;
  max_drawdown: number | string | null;
  total_return: number | string | null;
  annualized_return: number | string | null;
  user_id: string;
  created_at: string;
}
