import type { BacktestConfig, FactorConfig, OptimizeRequest, PerformanceRequest, Top10Row } from '../types/backtest';
import type { AssetTypeRow, ProductRow } from '../types/refdata';
import { isSingleFactorRow, multiFactorParams } from './top10';

function wireValue<T>(camel: unknown, snake: unknown, fallback: T): T {
  if (camel !== undefined) return camel as T;
  if (snake !== undefined) return snake as T;
  return fallback;
}

export function effectiveSymbol(cfg: BacktestConfig): string {
  return cfg.vendorSymbol || cfg.symbol;
}

/**
 * Build an OptimizeRequest from form state.
 *
 * The backend always accepts the unified factor-list shape. A single
 * factor config is just a 1-element ``factors`` array — there is no
 * "single mode" branch. Cross-product overrides on ``factors[i]``
 * (symbol / vendor_symbol / data_source) flow through unchanged.
 *
 * ``conjunction`` is only included when there are 2+ factors — it is
 * meaningless for a single-factor run, so we omit it from the wire
 * payload to match the backend schema (``conjunction: str | None``).
 */
export function buildOptimizeRequest(cfg: BacktestConfig): OptimizeRequest {
  const ds = cfg.dataSource;
  return {
    symbol: effectiveSymbol(cfg),
    start: cfg.start,
    end: cfg.end,
    trading_period: cfg.tradingPeriod,
    fee_bps: cfg.feeBps,
    data_source: ds,
    tm_interval_id: cfg.tmIntervalId,
    refresh_dataset: cfg.refreshDataset,
    factors: cfg.factors,
    ...(cfg.factors.length > 1 ? { conjunction: cfg.conjunction } : {}),
    walk_forward: cfg.walkForward,
    split_ratio: cfg.splitRatio,
  };
}

/**
 * Inverse of `buildOptimizeRequest`.
 *
 * Stored `CONFIG_JSON` is the wire payload (snake_case). Spreading it onto
 * `BacktestConfig` left `dataSource`, `tmIntervalId`, `tradingPeriod` and
 * the rest at `DEFAULT_CONFIG`, so Re-backtest / Clone opened Yahoo daily
 * 365 for an hourly Bybit run. Asset type is not on the wire — it is
 * recovered from `INST.PRODUCT` when the cusip is known.
 */
export function configFromOptimizeRequest(
  raw: Record<string, unknown> | null | undefined,
  defaults: BacktestConfig,
  lookup?: { products?: ProductRow[]; assetTypes?: AssetTypeRow[] },
): BacktestConfig {
  if (!raw) return { ...defaults };

  const wireSymbol = typeof raw.symbol === 'string' ? raw.symbol : defaults.symbol;
  const products = lookup?.products ?? [];
  const known = products.find(p => p.internal_cusip === wireSymbol);
  const asCusip = Boolean(known) || wireSymbol.includes('.');

  let assetType = typeof raw.assetType === 'string' && raw.assetType
    ? raw.assetType
    : defaults.assetType;
  if (!assetType && known && lookup?.assetTypes) {
    const at = lookup.assetTypes.find(a => a.asset_type_id === known.asset_type_id);
    if (at) assetType = at.display_name;
  }

  const factors = Array.isArray(raw.factors)
    ? raw.factors as FactorConfig[]
    : defaults.factors;

  return {
    ...defaults,
    symbol: asCusip ? wireSymbol : '',
    vendorSymbol: asCusip
      ? (typeof raw.vendorSymbol === 'string' ? raw.vendorSymbol : '')
      : wireSymbol,
    dataSource: wireValue(raw.dataSource, raw.data_source, defaults.dataSource),
    assetType,
    tmIntervalId: wireValue(raw.tmIntervalId, raw.tm_interval_id, defaults.tmIntervalId),
    start: typeof raw.start === 'string' ? raw.start : defaults.start,
    end: typeof raw.end === 'string' ? raw.end : defaults.end,
    tradingPeriod: wireValue(raw.tradingPeriod, raw.trading_period, defaults.tradingPeriod),
    feeBps: wireValue(raw.feeBps, raw.fee_bps, defaults.feeBps),
    refreshDataset: wireValue(raw.refreshDataset, raw.refresh_dataset, defaults.refreshDataset),
    conjunction: typeof raw.conjunction === 'string' ? raw.conjunction : defaults.conjunction,
    factors,
    walkForward: wireValue(raw.walkForward, raw.walk_forward, defaults.walkForward),
    splitRatio: wireValue(raw.splitRatio, raw.split_ratio, defaults.splitRatio),
  };
}

/**
 * Build a PerformanceRequest from form state + a selected top-10 row.
 *
 * 1-factor optimizer rows carry plain ``window`` / ``signal``;
 * 2+ factor rows carry ``window_0`` / ``signal_0`` / ... — both shapes
 * collapse to the same ``windows: number[]`` / ``signals: number[]``
 * payload.
 */
export function buildPerformanceRequest(cfg: BacktestConfig, row: Top10Row): PerformanceRequest {
  const ds = cfg.dataSource;
  let windows: number[];
  let signals: number[];
  if (isSingleFactorRow(row)) {
    if (cfg.factors.length !== 1) {
      throw new Error('buildPerformanceRequest: single-factor row used with multi-factor config');
    }
    windows = [row.window];
    signals = [row.signal];
  } else {
    ({ windows, signals } = multiFactorParams(row));
  }
  if (windows.length !== cfg.factors.length || signals.length !== cfg.factors.length) {
    throw new Error(
      `buildPerformanceRequest: row params length (${windows.length}/${signals.length}) ` +
      `does not match factors length (${cfg.factors.length})`,
    );
  }
  return {
    symbol: effectiveSymbol(cfg),
    start: cfg.start,
    end: cfg.end,
    trading_period: cfg.tradingPeriod,
    fee_bps: cfg.feeBps,
    data_source: ds,
    tm_interval_id: cfg.tmIntervalId,
    refresh_dataset: cfg.refreshDataset,
    factors: cfg.factors,
    ...(cfg.factors.length > 1 ? { conjunction: cfg.conjunction } : {}),
    windows,
    signals,
  };
}
