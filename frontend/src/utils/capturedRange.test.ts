import { describe, expect, it } from 'vitest';
import { capturedRange, isoDate, nextDay, rangeFits } from './capturedRange';
import type { Coverage } from '../types/marketData';

const coverage = (overrides: Partial<Coverage> = {}): Coverage => ({
  first_bar: '2020-03-25T00:00:00Z',
  last_bar: '2026-08-29T00:00:00Z',
  gaps: 0,
  error: null,
  ...overrides,
});

describe('capturedRange', () => {
  it('reads the stored bounds as plain dates', () => {
    expect(capturedRange(coverage())).toEqual({
      first: '2020-03-25',
      last: '2026-08-29',
      latestEnd: '2026-08-30',
    });
  });

  it('is null while coverage has not loaded', () => {
    expect(capturedRange(undefined)).toBeNull();
  });

  it('is null for a series with nothing captured', () => {
    expect(capturedRange(coverage({ first_bar: null, last_bar: null }))).toBeNull();
  });

  // The bug this guards, from a real FAILED run: Bybit's first hourly
  // BTCUSDT bar is 2020-03-25 10:00, the drawer snapped the start to
  // 2020-03-25, and the server refused a window reaching ten hours before
  // any bar existed. A date input cannot say 10:00, so the head rounds up.
  it('rounds an intraday head up to the first whole day it can serve', () => {
    expect(
      capturedRange(coverage({ first_bar: '2020-03-25T10:00:00+00:00' }))?.first,
    ).toBe('2020-03-26');
  });

  it('leaves a head already on midnight alone', () => {
    expect(capturedRange(coverage())?.first).toBe('2020-03-25');
  });

  it('gives an intraday tail no extra day', () => {
    // Today's date already covers an unclosed hourly bar; a whole day past
    // it is a window the server refuses.
    expect(
      capturedRange(coverage({ last_bar: '2026-09-03T14:00:00+00:00' }))?.latestEnd,
    ).toBe('2026-09-03');
  });

  it('rolls the head over a month end', () => {
    expect(
      capturedRange(coverage({ first_bar: '2020-03-31T10:00:00+00:00' }))?.first,
    ).toBe('2020-04-01');
  });
});

describe('isoDate', () => {
  it('trims a timestamp to what a date input takes', () => {
    expect(isoDate('2020-03-25T00:00:00Z')).toBe('2020-03-25');
  });
});

describe('nextDay', () => {
  it('advances one day', () => {
    expect(nextDay('2026-08-29')).toBe('2026-08-30');
  });

  it('rolls over a month end', () => {
    expect(nextDay('2026-08-31')).toBe('2026-09-01');
  });

  it('rolls over a leap day', () => {
    expect(nextDay('2028-02-28')).toBe('2028-02-29');
  });
});

describe('rangeFits', () => {
  const captured = { first: '2020-03-25', last: '2026-08-29', latestEnd: '2026-08-30' };

  it('accepts a window inside the captured bounds', () => {
    expect(rangeFits(captured, '2021-01-01', '2026-01-01')).toBe(true);
  });

  it('accepts the captured bounds exactly', () => {
    expect(rangeFits(captured, '2020-03-25', '2026-08-29')).toBe(true);
  });

  it('accepts an end of today, whose bar has not closed', () => {
    // The default end date is today. Refusing it would refuse every run
    // made before the daily close, over a bar that cannot exist yet.
    expect(rangeFits(captured, '2020-03-25', '2026-08-30')).toBe(true);
  });

  it('rejects a tail more than one bar past the last close', () => {
    expect(rangeFits(captured, '2020-03-25', '2026-08-31')).toBe(false);
  });

  it('rejects a start before the first captured bar', () => {
    expect(rangeFits(captured, '2016-01-01', '2026-08-29')).toBe(false);
  });

  it('gives the head no slack at all', () => {
    expect(rangeFits(captured, '2020-03-24', '2026-08-29')).toBe(false);
  });

  it('agrees with what the drawer snapped for an intraday series', () => {
    // The whole point of the head rounding: what the snap offers must be a
    // window this predicate — and therefore the server — accepts.
    const hourly = capturedRange({
      first_bar: '2020-03-25T10:00:00+00:00',
      last_bar: '2026-09-03T14:00:00+00:00',
      gaps: 0,
      error: null,
    })!;
    expect(rangeFits(hourly, hourly.first, hourly.last)).toBe(true);
    expect(rangeFits(hourly, '2020-03-25', hourly.last)).toBe(false);
  });
});
