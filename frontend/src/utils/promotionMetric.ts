import type { PromotionRow } from '../types/promotion';
import { toFiniteNumber } from './format';

/** Shredded BT.RESULT columns exposed on PromotionRow (from metric_key). */
const RESULT_METRIC_FIELDS = new Set<keyof PromotionRow>([
  'sharpe_ratio',
  'calmar_ratio',
  'max_drawdown',
  'total_return',
  'annualized_return',
]);

/** Map REFDATA.PROMOTION_METRIC.metric_key → PromotionRow shredded field. */
export function metricKeyToResultField(metricKey: string): keyof PromotionRow | null {
  const field = metricKey.toLowerCase().replace(/\s+/g, '_') as keyof PromotionRow;
  return RESULT_METRIC_FIELDS.has(field) ? field : null;
}

export function readPromotionMetric(row: PromotionRow, metricKey: string): number | null {
  const field = metricKeyToResultField(metricKey);
  if (!field) return null;
  return toFiniteNumber(row[field]);
}
