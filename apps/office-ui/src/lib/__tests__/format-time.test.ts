import { describe, it, expect } from 'vitest';
import { formatDuration } from '../format-time';

describe('formatDuration', () => {
  it('formats seconds, minutes and hours compactly', () => {
    expect(formatDuration(42.4)).toBe('42s');
    expect(formatDuration(725)).toBe('12m 5s');
    expect(formatDuration(720)).toBe('12m');
    expect(formatDuration(3725.4)).toBe('1h 2m');
    expect(formatDuration(7200)).toBe('2h');
  });

  it('returns an empty string for unusable input', () => {
    expect(formatDuration(-1)).toBe('');
    expect(formatDuration(Number.NaN)).toBe('');
  });
});
