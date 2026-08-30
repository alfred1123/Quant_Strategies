import type { Coverage } from '../types/marketData';

/**
 * The window a backtest can actually be run over, read from what has been
 * captured rather than typed by the user.
 *
 * An exchange backtest reads `MARKET_DATA.PRICE_BAR`, so the store — not the
 * calendar and not the venue's own retention — is the honest bound. Asking
 * for 2016 on a series whose first Bybit bar is 2020-03-25 is not a range the
 * run can narrow into silently; it is refused, and the user has no way to
 * guess the number that would have worked.
 */
export interface CapturedRange {
  first: string;
  last: string;
}

/** Trim an API timestamp to the `YYYY-MM-DD` the date inputs use. */
export function isoDate(ts: string): string {
  return ts.slice(0, 10);
}

/** One day on, in UTC — the slack the tail is allowed (see `rangeFits`). */
export function nextDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

/** What is stored for a series, or null while unknown or empty. */
export function capturedRange(coverage: Coverage | undefined): CapturedRange | null {
  if (!coverage?.first_bar || !coverage.last_bar) return null;
  return { first: isoDate(coverage.first_bar), last: isoDate(coverage.last_bar) };
}

/**
 * Whether a requested window can be served from `captured`.
 *
 * The tail gets one day of slack and the head gets none, mirroring
 * `_fetch_exchange_df`: an end of *today* is the ordinary request and today's
 * daily bar has not closed, so requiring the store to reach it would flag
 * every run made before the close. A bar that cannot exist yet is not a gap.
 * ISO dates compare correctly as strings.
 */
export function rangeFits(captured: CapturedRange, start: string, end: string): boolean {
  return start >= captured.first && end <= nextDay(captured.last);
}
