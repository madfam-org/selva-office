/**
 * Unit tests for /bundles page helpers.
 *
 * Pure logic — no React, no server fetch. These guard the à-la-carte
 * math so a CatalogProduct schema drift or bundle-price format change
 * fails loudly before the public /bundles page renders wrong savings
 * numbers to prospective customers.
 */
import { describe, expect, it } from 'vitest';

import {
  computeSavings,
  fmtUsd,
  resolveLine,
  sumMonthlyUsd,
  type CatalogResponse,
  type ResolvedLine,
} from '../helpers';

const CATALOG: CatalogResponse = {
  products: [
    {
      slug: 'dhanam',
      name: 'Dhanam',
      tiers: [
        {
          tierSlug: 'essentials',
          displayName: 'Essentials',
          prices: { USD: { monthly: 499, yearly: 4790 } },
        },
        {
          tierSlug: 'pro',
          displayName: 'Pro',
          prices: { USD: { monthly: 1499, yearly: 14388 } },
        },
      ],
    },
    {
      slug: 'selva',
      name: 'Selva',
      tiers: [
        {
          tierSlug: 'team',
          displayName: 'Team',
          prices: { USD: { monthly: 14900, yearly: null } },
        },
      ],
    },
    {
      slug: 'tezca',
      name: 'Tezca',
      tiers: [
        {
          tierSlug: 'enterprise',
          displayName: 'Enterprise',
          // Sales-led: empty prices object.
          prices: {},
        },
      ],
    },
  ],
};

// ---------------------------------------------------------------------------

describe('resolveLine', () => {
  it('finds product and tier in catalog', () => {
    const r = resolveLine(
      { product_slug: 'dhanam', tier_slug: 'pro' },
      CATALOG,
    );
    expect(r.product?.name).toBe('Dhanam');
    expect(r.tier?.tierSlug).toBe('pro');
    expect(r.monthly_usd).toBe(1499);
    expect(r.tier_label).toBe('Pro');
  });

  it('returns undefined product/tier when slug misses', () => {
    const r = resolveLine(
      { product_slug: 'missing', tier_slug: 'any' },
      CATALOG,
    );
    expect(r.product).toBeUndefined();
    expect(r.tier).toBeUndefined();
    expect(r.monthly_usd).toBeNull();
  });

  it('uses fallback_label when tier is missing', () => {
    const r = resolveLine(
      {
        product_slug: 'missing',
        tier_slug: 'any',
        fallback_label: 'Custom tier',
      },
      CATALOG,
    );
    expect(r.tier_label).toBe('Custom tier');
  });

  it('synthesises a tier label when no displayName and no fallback', () => {
    const catalogNoDisplayName: CatalogResponse = {
      products: [
        {
          slug: 'forj',
          name: 'Forj',
          tiers: [{ tierSlug: 'draft', displayName: null, prices: {} }],
        },
      ],
    };
    const r = resolveLine(
      { product_slug: 'forj', tier_slug: 'draft' },
      catalogNoDisplayName,
    );
    expect(r.tier_label).toBe('forj / draft');
  });

  it('returns null monthly_usd when tier has no USD price (sales-led)', () => {
    const r = resolveLine(
      { product_slug: 'tezca', tier_slug: 'enterprise' },
      CATALOG,
    );
    expect(r.monthly_usd).toBeNull();
  });

  it('returns null product when catalog is null (offline mode)', () => {
    const r = resolveLine({ product_slug: 'dhanam', tier_slug: 'pro' }, null);
    expect(r.product).toBeUndefined();
    expect(r.monthly_usd).toBeNull();
  });
});

// ---------------------------------------------------------------------------

describe('sumMonthlyUsd', () => {
  it('sums across resolved lines treating null as zero', () => {
    const resolved: ResolvedLine[] = [
      { product: undefined, tier: undefined, monthly_usd: 499, tier_label: 'a' },
      { product: undefined, tier: undefined, monthly_usd: 1499, tier_label: 'b' },
      { product: undefined, tier: undefined, monthly_usd: null, tier_label: 'c' },
    ];
    expect(sumMonthlyUsd(resolved)).toBe(1998);
  });

  it('returns 0 on empty input', () => {
    expect(sumMonthlyUsd([])).toBe(0);
  });
});

// ---------------------------------------------------------------------------

describe('fmtUsd', () => {
  it('formats cents as rounded USD', () => {
    expect(fmtUsd(499)).toMatch(/\$5\b/);
    expect(fmtUsd(14900)).toMatch(/\$149\b/);
  });

  it('rounds down to whole dollars', () => {
    // $4.99 → $5 (because maximumFractionDigits = 0)
    expect(fmtUsd(499)).not.toContain('.');
  });
});

// ---------------------------------------------------------------------------

describe('computeSavings', () => {
  const RESOLVED: ResolvedLine[] = [
    { product: undefined, tier: undefined, monthly_usd: 499, tier_label: 'a' },
    { product: undefined, tier: undefined, monthly_usd: 2999, tier_label: 'b' },
    { product: undefined, tier: undefined, monthly_usd: 1999, tier_label: 'c' },
  ];

  it('computes savings vs a point bundle price', () => {
    const r = computeSavings(RESOLVED, { monthly: 4499 });
    expect(r.alaCarteCents).toBe(5497);
    expect(r.savingsCents).toBe(998);
    expect(r.savingsPct).toBeCloseTo(18.16, 1);
  });

  it('uses high end of a range for conservative savings claim', () => {
    const r = computeSavings(RESOLVED, { range_monthly: [149900, 199900] });
    // Bundle high end = $1,999 > à-la-carte — so no savings.
    expect(r.savingsCents).toBeLessThanOrEqual(0);
    expect(r.savingsPct).toBe(0);
  });

  it('returns zero savings when bundle costs more', () => {
    const r = computeSavings(RESOLVED, { monthly: 10000 });
    expect(r.savingsPct).toBe(0);
  });

  it('handles empty à-la-carte without NaN', () => {
    const r = computeSavings([], { monthly: 4499 });
    expect(r.alaCarteCents).toBe(0);
    expect(r.savingsPct).toBe(0);
  });

  it('handles zero-cost à-la-carte (all sales-led) without NaN', () => {
    const resolved: ResolvedLine[] = [
      { product: undefined, tier: undefined, monthly_usd: null, tier_label: 'a' },
      { product: undefined, tier: undefined, monthly_usd: null, tier_label: 'b' },
    ];
    const r = computeSavings(resolved, { range_monthly: [100000, 200000] });
    expect(r.alaCarteCents).toBe(0);
    expect(r.savingsPct).toBe(0);
  });
});
