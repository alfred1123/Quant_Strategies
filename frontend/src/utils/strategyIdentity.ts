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
 * The traded leg carries its venue (`TRADE@VENUE`) because the same
 * recipe fitted on Yahoo prints and on Bybit prints is two different
 * strategies, not one. Naming only the factors let a Yahoo-traded run
 * read `... on bybit:price` — the label named the factor's venue while
 * the series being traded came from somewhere else — and collapsed both
 * venues onto a single identity, so their results grouped together.
 */
export function buildStrategyNm(cfg: BacktestConfig): string {
  const trade = effectiveSymbol(cfg);
  const parts = cfg.factors.map((f) => factorRecipe(f, trade));
  const factors = parts.join(cfg.factors.length > 1 ? ` ${cfg.conjunction} ` : '');
  return `${trade}@${cfg.dataSource} ← ${factors}`;
}

/** Stable group key for promotion / jobs UI (owner + canonical name). */
export function strategyGroupKey(userId: string, strategyNm: string | null, strategyId: string): string {
  return `${userId}\0${strategyNm ?? strategyId}`;
}
