/** Mirrors quant/schemas/market_data.py — bar capture subscriptions. */

/**
 * What has actually been captured for one series.
 *
 * `gaps` counts missing boundaries *between* the bounds, so it says nothing
 * about history older than `first_bar` — that is what backfill is for.
 * `error` is set when the venue could not be reached to answer, so one dead
 * exchange degrades a single row instead of failing the list.
 */
export interface Coverage {
  first_bar: string | null;
  last_bar: string | null;
  gaps: number | null;
  error: string | null;
}

export interface BarSubscriptionRow {
  bar_subscription_id: string;
  bar_subscription_vid: number;
  internal_cusip: string;
  tm_interval_id: number;
  source_app_id: number;
  is_enabled_ind: 'Y' | 'N';
  backfill_from_ts: string | null;
  transact_from_ts: string;
  coverage: Coverage;
}

/**
 * Create a subscription, or version one that exists.
 *
 * Sending `bar_subscription_id` edits that row — enable, disable, retarget —
 * rather than creating a second request for the same series.
 */
export interface SubscribeRequest {
  internal_cusip: string;
  tm_interval_id: number;
  source_app_id: number;
  is_enabled_ind?: 'Y' | 'N';
  backfill_from_ts?: string | null;
  bar_subscription_id?: string;
}

/**
 * How far back a venue will actually serve one series.
 *
 * The floor on any capture target. Without it "history wanted from" is a date
 * the user invents, and one before the pair listed can never be met — the row
 * then reports a shortfall against history that was never obtainable.
 */
export interface VenueDepth {
  earliest: string | null;
  bars_available: number | null;
  max_backfill_bars: number;
}

export interface BackfillRequest {
  internal_cusip: string;
  tm_interval_id: number;
  source_app_id: number;
  start: string;
  end?: string | null;
}

/** What a fill managed, and what the venue would not serve. */
export interface BackfillReport {
  start: string;
  end: string;
  expected: number;
  missing: number;
  inserted: number;
  unfilled: string[];
  is_continuous: boolean;
}
