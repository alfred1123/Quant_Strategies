// Mirrors api/schemas/promotion.py — keep in sync.

export interface GateResult {
  name: string;
  passed: boolean;
  value: number | null;
  threshold: number | null;
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
  sharpe_ratio: number | null;
  calmar_ratio: number | null;
  max_drawdown: number | null;
  total_return: number | null;
  annualized_return: number | null;
  user_id: string;
  created_at: string;
}
