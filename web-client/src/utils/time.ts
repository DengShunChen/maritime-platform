/**
 * Normalize backend time_points to Unix milliseconds.
 * app_v2 returns ms; legacy app.py returned seconds.
 */
export function normalizeTimePointsToMs(values: number[]): number[] {
  if (values.length === 0) return [];

  return values.map((t) => (t > 1e12 ? t : t * 1000));
}
