/** Mirrors quant/api/schemas/strategies.py — keep in sync. */

export interface StrategyListRow {
  strategy_id: string;
  strategy_vid: number;
  strategy_nm: string | null;
  is_best_ind: string;
  created_at: string;
  sharpe_ratio: number | null;
  calmar_ratio: number | null;
  max_drawdown: number | null;
  total_return: number | null;
  annualized_return: number | null;
}

export type StrategyListVersions = 'best' | 'all';

/** Optional react-router state when navigating to Trade Apply. */
export interface TradeApplyLocationState {
  strategyId?: string;
  strategyVid?: number;
  strategyNm?: string | null;
  queueId?: string;
}
