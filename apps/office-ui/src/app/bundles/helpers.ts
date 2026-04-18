/**
 * Pure helpers for the /bundles page.
 *
 * Extracted so they can be unit-tested without rendering the
 * React server component. The page.tsx imports these directly.
 */

export interface CatalogPrice {
  monthly: number | null;
  yearly: number | null;
}
export interface CatalogTier {
  tierSlug: string;
  displayName: string | null;
  prices: Record<string, CatalogPrice>;
}
export interface CatalogProduct {
  slug: string;
  name: string;
  tiers: CatalogTier[];
}
export interface CatalogResponse {
  products: CatalogProduct[];
}

export interface BundleLine {
  product_slug: string;
  tier_slug: string;
  fallback_label?: string;
}

export interface ResolvedLine {
  product: CatalogProduct | undefined;
  tier: CatalogTier | undefined;
  monthly_usd: number | null;
  tier_label: string;
}

export function resolveLine(
  line: BundleLine,
  catalog: CatalogResponse | null,
): ResolvedLine {
  const product = catalog?.products.find((p) => p.slug === line.product_slug);
  const tier = product?.tiers.find((t) => t.tierSlug === line.tier_slug);
  const monthly_usd = tier?.prices?.USD?.monthly ?? null;
  const tier_label =
    tier?.displayName ??
    line.fallback_label ??
    `${line.product_slug} / ${line.tier_slug}`;
  return { product, tier, monthly_usd, tier_label };
}

export function sumMonthlyUsd(resolved: ResolvedLine[]): number {
  return resolved.reduce((acc, r) => acc + (r.monthly_usd ?? 0), 0);
}

export function fmtUsd(cents: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

export interface SavingsResult {
  alaCarteCents: number;
  savingsCents: number;
  savingsPct: number;
}

/**
 * Compute savings against either a point bundle price or a range.
 * For ranges we compare à-la-carte to the high end (conservative).
 */
export function computeSavings(
  resolved: ResolvedLine[],
  bundlePrice: { monthly: number } | { range_monthly: [number, number] },
): SavingsResult {
  const alaCarteCents = sumMonthlyUsd(resolved);
  let bundleCents: number | null = null;
  if ('monthly' in bundlePrice) {
    bundleCents = bundlePrice.monthly;
  } else {
    bundleCents = bundlePrice.range_monthly[1]; // high end
  }
  const savingsCents = bundleCents != null ? alaCarteCents - bundleCents : 0;
  const savingsPct =
    alaCarteCents > 0 && savingsCents > 0
      ? (savingsCents / alaCarteCents) * 100
      : 0;
  return { alaCarteCents, savingsCents, savingsPct };
}
