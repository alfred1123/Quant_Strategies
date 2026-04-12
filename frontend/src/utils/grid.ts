/** Number of discrete steps in a range: floor((max - min) / step) + 1, minimum 1. */
export function countSteps(r: { min: number; max: number; step: number }): number {
  if (r.step <= 0) return 1;
  return Math.max(1, Math.floor((r.max - r.min) / r.step) + 1);
}
