export interface IndicatorRow {
  method_name: string;
  display_name: string;
  win_min: number;
  win_max: number;
  win_step: number;
  sig_min: number | null;
  sig_max: number | null;
  sig_step: number;
  is_bounded_ind: string | null;
}

export interface SignalTypeRow {
  name: string;
  display_name: string;
}

export interface AssetTypeRow {
  asset_type_id: number;
  name: string;
  display_name: string;
  trading_period: number;
}

export interface ConjunctionRow {
  name: string;
  display_name: string;
}

export interface PromotionStateRow {
  promotion_state_id: number;
  name: string;
  display_name: string | null;
  description: string | null;
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

export interface DataColumnRow {
  column_name: string;
  display_name: string;
}

/**
 * Bar / schedule cadence. `display_name` is nullable only so the UI keeps
 * working against a database that predates the 1.7.0 refdata migration.
 */
export interface TmIntervalRow {
  tm_interval_id: number;
  name: string;
  display_name: string | null;
  period_length: string;
  description: string | null;
}

export interface AppRow {
  app_id: number;
  name: string;
  display_name: string;
  class_name: string;
  is_exchange_ind: 'Y' | 'N';
  description: string | null;
}

export interface ProductRow {
  product_id: number;
  product_vid: number;
  internal_cusip: string;
  display_nm: string;
  asset_type_id: number;
  exchange: string | null;
  /** Nullable on the column, and nothing guaranteed it before the create form. */
  ccy: string | null;
  description: string | null;
}

/** A product as one venue lists it: the product, plus the ticker it prints. */
export interface ListedProduct extends ProductRow {
  vendor_symbol: string;
}

/**
 * A ticker a venue currently prints, read live from the exchange via ccxt.
 *
 * Not a platform row: this is what *could* be mapped, which is exactly the set
 * `ProductRow` and `XrefRow` cannot answer for a new instrument.
 */
export interface VenueSymbol {
  /** Exactly what goes in `vendor_symbol` — the raw ticker, not `BTC/USDT`. */
  vendor_symbol: string;
  base: string | null;
  quote: string | null;
  /** `['spot', 'swap']` where one ticker means both, as Bybit's majors do. */
  market_types: string[];
}

export interface XrefRow {
  product_xref_id: number;
  product_xref_vid: number;
  product_id: number;
  app_id: number;
  vendor_symbol: string;
}

/**
 * One new instrument: the product's identity plus the first venue that lists
 * it. `app_id` and `vendor_symbol` describe the `INST.PRODUCT_XREF` row rather
 * than the product — a product with no xref is invisible to every venue-scoped
 * list, so the two are created together.
 */
export interface CreateInstrumentRequest {
  /** Lowercase `{symbol}.{suffix}`, one per logical instrument (decision #21). */
  internal_cusip: string;
  display_nm: string;
  asset_type_id: number;
  /** Listing/clearing venue — equities only, `null` on `.crypto` spot. */
  exchange: string | null;
  /** Quote currency of the pair traded, e.g. `USDT`. */
  ccy: string | null;
  description: string | null;
  app_id: number;
  vendor_symbol: string;
}

/** The product and xref rows the insert created, each with its first version. */
export interface CreatedInstrument {
  product_id: number;
  product_vid: number;
  internal_cusip: string;
  display_nm: string;
  /** Required on the request, so anything this route creates has one. */
  asset_type_id: number;
  exchange: string | null;
  ccy: string | null;
  description: string | null;
  app_id: number;
  vendor_symbol: string;
  product_xref_id: number;
  product_xref_vid: number;
}
