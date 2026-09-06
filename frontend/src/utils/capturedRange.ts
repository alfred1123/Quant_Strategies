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
  /** The first stored bar, exactly — a whole day, or an instant if intraday. */
  first: string;
  /** The last stored bar, same form as `first`. */
  last: string;
  /** Latest end the server accepts: `last` plus one bar of slack. */
  latestEnd: string;
  /**
   * Whether these bounds carry a time of day, so the inputs know which
   * control to render. An intraday series cannot be expressed by a date.
   */
  intraday: boolean;
}

/** Trim an API timestamp to the `YYYY-MM-DD` the date inputs use. */
export function isoDate(ts: string): string {
  return ts.slice(0, 10);
}

/** Trim an API timestamp to the `YYYY-MM-DDTHH:mm` a datetime input uses. */
export function isoMinute(ts: string): string {
  return ts.slice(0, 16);
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
 * The bounds are reported **as stored**, to the minute when the series is
 * intraday. Rounding either way is what broke this: Bybit's first hourly
 * `BTCUSDT` bar is 2020-03-25 10:00, and a date can only say 2020-03-25 —
 * ten hours that never existed, which `_fetch_exchange_df` refuses because
 * the head gets no slack. Rounding *up* to 2020-03-26 was accepted but threw
 * away a day of history to work around a field that could not hold a time.
 * So the field holds a time instead, and the bound stays the true one.
 *
 * A daily series still reads as plain dates: its bars sit on midnight, so
 * there is no time of day to lose and no reason to show one.
 */
export function capturedRange(coverage: Coverage | undefined): CapturedRange | null {
  if (!coverage?.first_bar || !coverage.last_bar) return null;
  const intraday =
    !onWholeDay(coverage.first_bar) || !onWholeDay(coverage.last_bar);
  if (!intraday) {
    const lastDay = isoDate(coverage.last_bar);
    return {
      first: isoDate(coverage.first_bar),
      last: lastDay,
      // One *bar* of slack: an end of today is the ordinary request and
      // today's bar has not closed, so demanding the store reach it would
      // flag every run made before the close.
      latestEnd: nextDay(lastDay),
      intraday: false,
    };
  }
  return {
    first: isoMinute(coverage.first_bar),
    last: isoMinute(coverage.last_bar),
    // The stored last bar itself, not a day on. The server allows one bar of
    // slack past it, so this is inside what it accepts whatever the period —
    // which a whole day would not be for an hourly series.
    latestEnd: isoMinute(coverage.last_bar),
    intraday: true,
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

/**
 * The window every series in a run can actually serve.
 *
 * Each exchange fetch must cover the requested range in full, so a BTC
 * snap of 2020-03-25 10:00 on an ETH series that starts 2021-03-15 is
 * refused rather than shortened. The overlap is the only range that
 * would not produce that refusal.
 */
export function coverageIntersection(ranges: CapturedRange[]): CapturedRange | null {
  if (ranges.length === 0) return null;
  let first = ranges[0].first;
  let last = ranges[0].last;
  let latestEnd = ranges[0].latestEnd;
  let intraday = ranges[0].intraday;
  for (const r of ranges.slice(1)) {
    if (r.first > first) first = r.first;
    if (r.last < last) last = r.last;
    if (r.latestEnd < latestEnd) latestEnd = r.latestEnd;
    if (r.intraday) intraday = true;
  }
  if (first > last) return null;
  return { first, last, latestEnd, intraday };
}

/** Snap a requested window onto captured bounds when it would be refused. */
export function fitToCaptured(
  captured: CapturedRange,
  start: string,
  end: string,
): { start: string; end: string } {
  if (rangeFits(captured, start, end)) return { start, end };
  return { start: captured.first, end: captured.last };
}
