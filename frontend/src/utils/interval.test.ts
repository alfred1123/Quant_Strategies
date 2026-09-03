import { describe, it, expect } from 'vitest';
import { barsPerDay, periodSeconds } from './interval';

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
