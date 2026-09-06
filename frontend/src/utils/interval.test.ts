import { describe, it, expect } from 'vitest';
import { barsPerDay, periodSeconds, scaleWindowRange } from './interval';

/**
 * The same column reaches the browser in three spellings, because a Postgres
 * interval is stringified by `str()` on its way into Redis.
 */
describe('periodSeconds', () => {
  it.each([
    ['1 day, 0:00:00', 86_400],
    ['1 day', 86_400],
    ['01:00:00', 3_600],
    ['1:00:00', 3_600],
    ['0:15:00', 900],
    ['0:01:00', 60],
    ['7 days, 0:00:00', 604_800],
  ])('reads %s as %i seconds', (input, expected) => {
    expect(periodSeconds(input)).toBe(expected);
  });

  it('returns null for something it cannot read', () => {
    expect(periodSeconds('every so often')).toBeNull();
  });

  it('returns null rather than zero for an empty interval', () => {
    // Zero would divide into Infinity bars a day one caller down.
    expect(periodSeconds('0:00:00')).toBeNull();
  });
});

describe('barsPerDay', () => {
  it('is 1 for daily', () => {
    expect(barsPerDay('1 day, 0:00:00')).toBe(1);
  });

  it('is 24 for hourly', () => {
    expect(barsPerDay('01:00:00')).toBe(24);
  });

  it('turns a 365-day annualisation into an hourly one', () => {
    expect(365 * barsPerDay('01:00:00')!).toBe(8_760);
  });

  it('is null when the period cannot be read', () => {
    expect(barsPerDay('nonsense')).toBeNull();
  });
});

describe('scaleWindowRange', () => {
  const daily = { min: 5, max: 100, step: 5 };

  it('turns a 100-bar daily max into 2,400 hourly bars', () => {
    // Same calendar lookback, same number of grid points: 5/100/5 → 20
    // steps becomes 120/2400/120 → still 20.
    expect(scaleWindowRange(daily, 1, 24)).toEqual({ min: 120, max: 2_400, step: 120 });
  });

  it('undoes hourly back to daily without compounding', () => {
    expect(scaleWindowRange({ min: 120, max: 2_400, step: 120 }, 24, 1)).toEqual(daily);
  });

  it('scales a 15-minute cadence by 96 bars a day', () => {
    expect(scaleWindowRange(daily, 1, 96)).toEqual({ min: 480, max: 9_600, step: 480 });
  });

  it('leaves the range alone when the cadence does not change', () => {
    expect(scaleWindowRange(daily, 1, 1)).toEqual(daily);
  });

  it('never lets step fall below 1', () => {
    expect(scaleWindowRange(daily, 24, 1).step).toBeGreaterThanOrEqual(1);
    expect(scaleWindowRange({ min: 5, max: 100, step: 5 }, 7, 1).step).toBe(1);
  });
});
