import type { BacktestConfig, FactorConfig } from '../types/backtest';
import { effectiveSymbol } from './requestBuilders';

function factorSource(f: FactorConfig, trade: string): string {
  return f.vendor_symbol || f.symbol || trade;
}

/** Per-factor recipe: SOURCE/INDICATOR/SIGNAL on METRIC. */
function factorRecipe(f: FactorConfig, trade: string): string {
  const src = factorSource(f, trade);
  const metric = f.data_source ? `${f.data_source}:${f.data_column}` : f.data_column;
  return `${src}/${f.indicator}/${f.strategy} on ${metric}`;
}

/**
 * Canonical STRATEGY_NM — used for DB identity lookup and UI display.
 *
 * The traded leg carries its venue and its cadence (`TRADE@VENUE:CADENCE`)
 * because both select an input series, and a `STRATEGY_ID` is the claim that
 * two runs are versions of one thing — which is also the instruction to
 * compare their metrics.
 *
 * Venue came first: the same recipe fitted on Yahoo prints and on Bybit
 * prints is two different strategies. Naming only the factors let a
 * Yahoo-traded run read `... on bybit:price` — the label named the factor's
 * venue while the series being traded came from somewhere else — and
 * collapsed both venues onto a single identity.
 *
 * Cadence is the same mistake one level down, and it is the more dangerous
 * one because it is arithmetic rather than a label. Picking hourly moves
 * `trading_period` from 365 to 8760, so Sharpe annualises by a factor of
 * ~4.9 and annualised return by 24. An hourly run sharing a lineage with
 * daily ones reaches `_evaluate_promotion`, which compares the numbers bare
 * and would hand `IS_BEST_IND` to whichever scale is larger — a strategy
 * promoted on units, then refused at deploy because `schedule_policy` only
 * allows the cadence it was fitted on.
 *
 * `cadence` is `REFDATA.TM_INTERVAL.NAME` (`DAILY`, `1H`), never the id:
 * renumbering the table must not fork every lineage on the platform.
 */
export function buildStrategyNm(cfg: BacktestConfig, cadence: string): string {
  const trade = effectiveSymbol(cfg);
  const parts = cfg.factors.map((f) => factorRecipe(f, trade));
  const factors = parts.join(cfg.factors.length > 1 ? ` ${cfg.conjunction} ` : '');
  return `${trade}@${cfg.dataSource}:${cadence} ← ${factors}`;
}

/** Stable group key for promotion / jobs UI (owner + canonical name). */
export function strategyGroupKey(userId: string, strategyNm: string | null, strategyId: string): string {
  return `${userId}\0${strategyNm ?? strategyId}`;
}
