import type { SeriesKey } from '../api/marketData';
import type { BacktestConfig } from '../types/backtest';
import type { AppRow } from '../types/refdata';

/**
 * Every exchange series a run will fetch — the traded leg plus any
 * factor that names its own product or inherits an exchange venue.
 *
 * `_fetch_exchange_df` requires each of these to cover the requested
 * start/end in full. The drawer therefore asks coverage for the set,
 * not only the traded product: leftover BTC dates on an ETH factor
 * (or an ETH product after a BTC snap) are how a job FAILED after the
 * warning had already named the mismatch.
 */
export function exchangeSeriesKeys(config: BacktestConfig, apps: AppRow[]): SeriesKey[] {
  if (config.tmIntervalId === null) return [];

  const keys: SeriesKey[] = [];
  const add = (cusip: string | undefined, sourceName: string | undefined) => {
    if (!cusip) return;
    const app = apps.find(a => a.name === sourceName);
    if (app?.is_exchange_ind !== 'Y') return;
    keys.push({
      internal_cusip: cusip,
      tm_interval_id: config.tmIntervalId as number,
      source_app_id: app.app_id,
    });
  };

  add(config.symbol.trim() || undefined, config.dataSource);
  for (const f of config.factors) {
    // Same source the worker uses: an unset factor source inherits
    // the traded venue. A leftover provider on the factor (DEFAULT
    // used to pin `data_source: 'yahoo'`) is *not* an inherit — that
    // is how ETH on Bybit was skipped while the hint still named BTC.
    add(
      (f.symbol || f.vendor_symbol) || undefined,
      f.data_source || config.dataSource,
    );
  }

  const seen = new Set<string>();
  return keys.filter(k => {
    const id = seriesKeyId(k);
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

export function seriesKeyId(key: SeriesKey): string {
  return `${key.internal_cusip}|${key.tm_interval_id}|${key.source_app_id}`;
}
