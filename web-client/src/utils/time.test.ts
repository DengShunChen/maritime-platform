import { describe, expect, it } from 'vitest';
import { normalizeTimePointsToMs } from './time';

describe('normalizeTimePointsToMs', () => {
  it('converts seconds to ms', () => {
    expect(normalizeTimePointsToMs([1700000000])).toEqual([1700000000000]);
  });

  it('keeps values already in ms', () => {
    expect(normalizeTimePointsToMs([1700000000000])).toEqual([1700000000000]);
  });

  it('handles mixed legacy and v2 responses', () => {
    expect(normalizeTimePointsToMs([1700000000, 1700003600000])).toEqual([
      1700000000000,
      1700003600000,
    ]);
  });

  it('returns empty for empty input', () => {
    expect(normalizeTimePointsToMs([])).toEqual([]);
  });
});
