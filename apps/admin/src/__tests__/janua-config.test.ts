// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { safeRedirectPath } from '../lib/janua-config';

describe('safeRedirectPath', () => {
  it.each([
    ['/', '/'],
    ['/agents?tab=active', '/agents?tab=active'],
    ['/billing#invoices', '/billing#invoices'],
  ])('keeps the same-origin path %s', (input, expected) => {
    expect(safeRedirectPath(input)).toBe(expected);
  });

  it.each([null, undefined, '', 'agents', 'https://example.com/', '//example.com', '/\\example.com', '/\nagents'])(
    'falls back to / for %s',
    (input) => {
      expect(safeRedirectPath(input as string | null | undefined)).toBe('/');
    },
  );
});
