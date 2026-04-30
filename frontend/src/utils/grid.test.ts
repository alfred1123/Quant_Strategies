import { describe, it, expect } from 'vitest';
import { countSteps } from './grid';

describe('countSteps', () => {
  it('returns correct count for a normal range', () => {
    expect(countSteps({ min: 5, max: 100, step: 5 })).toBe(20);
  });

  it('returns 1 when step <= 0', () => {
    expect(countSteps({ min: 0, max: 100, step: 0 })).toBe(1);
    expect(countSteps({ min: 0, max: 100, step: -5 })).toBe(1);
  });

  it('returns 1 when min equals max', () => {
    expect(countSteps({ min: 50, max: 50, step: 5 })).toBe(1);
  });

  it('returns 1 when min > max', () => {
    expect(countSteps({ min: 100, max: 5, step: 5 })).toBe(1);
  });

  it('handles fractional step sizes', () => {
    expect(countSteps({ min: 0.25, max: 2.5, step: 0.25 })).toBe(10);
  });

  it('floors partial steps', () => {
    expect(countSteps({ min: 0, max: 10, step: 3 })).toBe(4);
  });
});
