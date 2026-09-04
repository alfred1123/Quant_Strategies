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
  /** Earliest date the store serves in full — safe to put in a date input. */
  first: string;
  /** Date of the last stored bar. */
  last: string;
  /** Latest end date the server accepts: `last` plus one bar of slack. */
  latestEnd: string;
}

/** Trim an API timestamp to the `YYYY-MM-DD` the date inputs use. */
export function isoDate(ts: string): string {
  return ts.slice(0, 10);
}

/** One day on, in UTC. */
export function nextDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

/**
 * Whether a stored bound lands on a whole UTC day.
 *
 * Compared as text rather than through `Date`, because a timestamp without a
 * zone parses as *local* and would answer this question differently depending
 * on where the browser is. Bars are stored and served in UTC, which is the
 * same frame `_fetch_exchange_df` compares in.
 */
function onWholeDay(ts: string): boolean {
  return ts.length <= 10 || ts.slice(11, 19) === '00:00:00';
}

/**
 * What is stored for a series, or null while unknown or empty.
 *
 * `first` rounds **up** to the next whole day whenever the earliest bar is
 * intraday. A date input can only express midnight, and truncating an
 * intraday bound moves it backwards: Bybit's first hourly `BTCUSDT` bar is
 * 2020-03-25 10:00, so a start of `2020-03-25` asks for ten hours that have
 * never existed. `_fetch_exchange_df` gives the head no slack, so that start
 * is refused every time — and it was, on a run this snapping had produced.
 * A daily series is unaffected: its bars already sit on midnight. The cost is
 * at most one day at the front of an intraday series.
 */
export function capturedRange(coverage: Coverage | undefined): CapturedRange | null {
  if (!coverage?.first_bar || !coverage.last_bar) return null;
  const firstDay = isoDate(coverage.first_bar);
  const lastDay = isoDate(coverage.last_bar);
  return {
    first: onWholeDay(coverage.first_bar) ? firstDay : nextDay(firstDay),
    last: lastDay,
    // One *bar* of slack, not one day: an end of today is the ordinary
    // request and today's bar has not closed, so demanding the store reach
    // it would flag every run made before the close. On an intraday series
    // that unclosed bar is an hour, and today's date already covers it — a
    // whole day of slack there is a window the server will refuse.
    latestEnd: onWholeDay(coverage.last_bar) ? nextDay(lastDay) : lastDay,
  };
}

/**
 * Whether a requested window can be served from `captured`.
 *
 * Both bounds are already the servable dates, so this is the plain comparison
 * `_fetch_exchange_df` makes on instants. ISO dates compare correctly as
 * strings.
 */
export function rangeFits(captured: CapturedRange, start: string, end: string): boolean {
  return start >= captured.first && end <= captured.latestEnd;
}
