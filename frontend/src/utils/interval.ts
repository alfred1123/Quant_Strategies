/**
 * How a REFDATA cadence relates to a day.
 *
 * `TM_INTERVAL.PERIOD_LENGTH` is a Postgres interval serialised by
 * `json.dumps(default=str)` on the way into Redis, so it arrives as
 * `"1 day, 0:00:00"`, `"1 day"` or `"01:00:00"` depending on the value —
 * three spellings of the same column, which is why this is parsed rather
 * than matched against a name.
 */

const DAYS = /(\d+)\s*days?/;
const CLOCK = /(\d+):(\d{2}):(\d{2})/;

/** Seconds in one bar of this cadence, or `null` if unparseable. */
export function periodSeconds(periodLength: string): number | null {
  const days = DAYS.exec(periodLength);
  const clock = CLOCK.exec(periodLength);
  if (!days && !clock) return null;

  const fromDays = days ? Number(days[1]) * 86_400 : 0;
  const fromClock = clock
    ? Number(clock[1]) * 3_600 + Number(clock[2]) * 60 + Number(clock[3])
    : 0;
  const total = fromDays + fromClock;
  return total > 0 ? total : null;
}

/**
 * Bars this cadence produces in a day — the factor between a daily
 * annualisation and this one.
 *
 * `REFDATA.ASSET_TYPE.TRADING_PERIOD` counts periods per year on daily bars
 * (365 for a market that never closes, 252 for one that does). Annualised
 * return scales by that number and Sharpe by its square root, so an hourly
 * run left on the daily figure reports both far too low.
 */
export function barsPerDay(periodLength: string): number | null {
  const seconds = periodSeconds(periodLength);
  return seconds === null ? null : 86_400 / seconds;
}

/**
 * Indicator lookback is a bar count. `REFDATA.INDICATOR.WIN_*` are written
 * in daily bars (typically 5 / 100 / 5), so an hourly run left on those
 * numbers searches ~4 calendar days while daily searched ~100.
 *
 * Min, max, and step all move so the grid stays the same number of points
 * (~20). Scaling only max would explode exhaustive search. Signal range is
 * a threshold, not a bar count, and is not scaled.
 */
export function scaleWindowRange(
  range: { min: number; max: number; step: number },
  fromBarsPerDay: number,
  toBarsPerDay: number,
): { min: number; max: number; step: number } {
  if (fromBarsPerDay <= 0 || toBarsPerDay <= 0 || fromBarsPerDay === toBarsPerDay) {
    return range;
  }
  const scale = (n: number) => Math.max(1, Math.round((n * toBarsPerDay) / fromBarsPerDay));
  return { min: scale(range.min), max: scale(range.max), step: scale(range.step) };
}
