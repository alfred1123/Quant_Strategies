import type { PromotionRow } from '../types/promotion';
import { toFiniteNumber } from './format';

/** Shredded BT.RESULT strategy-metric columns on PromotionRow. */
const STRATEGY_METRIC_FIELDS = new Set<keyof PromotionRow>([
  'sharpe_ratio',
  'calmar_ratio',
  'max_drawdown',
  'total_return',
  'annualized_return',
]);

/** Shredded BT.RESULT buy-and-hold columns on PromotionRow. */
const BUY_HOLD_METRIC_FIELDS = new Set<keyof PromotionRow>([
  'buy_hold_sharpe_ratio',
  'buy_hold_calmar_ratio',
  'buy_hold_max_drawdown',
  'buy_hold_total_return',
  'buy_hold_annualized_return',
]);

function metricKeyToField(
  metricKey: string,
  fields: Set<keyof PromotionRow>,
): keyof PromotionRow | null {
  const field = metricKey.toLowerCase().replace(/\s+/g, '_') as keyof PromotionRow;
  return fields.has(field) ? field : null;
}

/** Map CONFIG.PROMOTION_METRIC.metric_key → strategy shredded field. */
export function metricKeyToResultField(metricKey: string): keyof PromotionRow | null {
  return metricKeyToField(metricKey, STRATEGY_METRIC_FIELDS);
}

/** Map CONFIG.PROMOTION_METRIC.metric_key → buy-and-hold shredded field. */
export function metricKeyToBuyHoldField(metricKey: string): keyof PromotionRow | null {
  const base = metricKeyToField(metricKey, STRATEGY_METRIC_FIELDS);
  if (!base) return null;
  const buyHold = (`buy_hold_${String(base)}`) as keyof PromotionRow;
  return BUY_HOLD_METRIC_FIELDS.has(buyHold) ? buyHold : null;
}

export function readPromotionMetric(row: PromotionRow, metricKey: string): number | null {
  const field = metricKeyToResultField(metricKey);
  if (!field) return null;
  return toFiniteNumber(row[field]);
}

export function readBuyHoldMetric(row: PromotionRow, metricKey: string): number | null {
  const field = metricKeyToBuyHoldField(metricKey);
  if (!field) return null;
  return toFiniteNumber(row[field]);
}

/** True when at least one SOFT metric has a buy-and-hold bench value. */
export function hasBuyHoldBenchmark(
  row: PromotionRow,
  metricKeys: string[],
): boolean {
  return metricKeys.some((key) => readBuyHoldMetric(row, key) != null);
}
