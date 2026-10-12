/**
 * Selva's plans as Dhanam publishes them.
 *
 * Pricing authority (owner ruling, 2026-10-11): Tulana authors the SKU tiers
 * and prices, Dhanam publishes them at `GET /v1/billing/catalog/<product>`
 * (public, no auth) and charges them. The pricing page renders from that
 * endpoint, so no price is typed into this repo and a catalog change needs no
 * Selva deploy.
 *
 * The browser cannot call the catalog itself (Dhanam sends no CORS allow-origin
 * for selva.town), so the page fetches it on the server, the same way
 * `/catalog` and `/bundles` do.
 */

export const SELVA_CATALOG_PRODUCT = 'selva';

/** Revalidate window for the catalog read; matches Dhanam's own cache-control. */
export const CATALOG_REVALIDATE_SECONDS = 300;

/** A Selva tier as the pricing page shows it. */
export interface SelvaPlan {
  /** Catalog tier slug (`developer`, `team`, `business`); checkout accepts it as is. */
  slug: string;
  name: string;
  /** MXN per month with 16% IVA, whole pesos rounded up. */
  mxnMonthlyGross: number;
  dailyTokenLimit: number | null;
  maxAgents: number | null;
  features: string[];
}

interface CatalogTier {
  tierSlug?: string;
  slug?: string;
  name?: string;
  displayName?: string | null;
  metadata?: Record<string, unknown> | null;
  prices?: Record<string, { monthly?: number | null } | undefined>;
  features?: unknown;
}

/**
 * The IVA-inclusive ceil rule, written exactly as dhanam's
 * `apps/web/e2e/helpers/catalog.ts` (`mxnGrossFromNetCentavos`) and
 * `@dhanam/shared` compute it, so this page cannot disagree with Dhanam's own
 * pages by a rounding artefact.
 */
export function mxnGrossFromNetCentavos(netCentavos: number): number {
  return Math.ceil((netCentavos / 100) * (1 + 0.16));
}

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * Maps a catalog product to the plans the page sells: every tier with a
 * monthly MXN price, in catalog order. Throws when the product carries no
 * such tier, so a malformed catalog shows the error state instead of an empty
 * grid.
 */
export function selvaPlansFromCatalog(product: unknown): SelvaPlan[] {
  const tiers = (product as { tiers?: unknown } | null)?.tiers;
  if (!Array.isArray(tiers)) {
    throw new Error('catalog product has no tiers array');
  }
  const plans: SelvaPlan[] = [];
  for (const raw of tiers as CatalogTier[]) {
    const slug = String(raw?.tierSlug ?? raw?.slug ?? '').trim();
    const netCentavos = raw?.prices?.MXN?.monthly;
    if (!slug || typeof netCentavos !== 'number' || !Number.isFinite(netCentavos)) continue;
    plans.push({
      slug,
      name: String(raw.displayName || raw.name || slug),
      mxnMonthlyGross: mxnGrossFromNetCentavos(netCentavos),
      dailyTokenLimit: numberOrNull(raw.metadata?.daily_token_limit),
      maxAgents: numberOrNull(raw.metadata?.max_agents),
      features: Array.isArray(raw.features)
        ? raw.features.filter((f): f is string => typeof f === 'string')
        : [],
    });
  }
  if (plans.length === 0) {
    throw new Error('catalog product has no tier with a monthly MXN price');
  }
  return plans;
}

/** Dhanam API origin, as `/catalog` and `/bundles` resolve it. */
export function dhanamApiBase(env: Record<string, string | undefined> = process.env): string {
  const base = env.DHANAM_API_URL || env.NEXT_PUBLIC_DHANAM_API_URL || 'https://api.dhan.am';
  return base.replace(/\/+$/, '').replace(/\/v1$/, '');
}

/**
 * Reads Selva's plans from the Dhanam catalog. Returns null (and logs why)
 * when the catalog is unreachable or malformed; the page then says it could
 * not load plans rather than inventing any.
 */
export async function fetchSelvaPlans(): Promise<SelvaPlan[] | null> {
  const url = `${dhanamApiBase()}/v1/billing/catalog/${SELVA_CATALOG_PRODUCT}`;
  try {
    const res = await fetch(url, { next: { revalidate: CATALOG_REVALIDATE_SECONDS } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return selvaPlansFromCatalog(await res.json());
  } catch (error) {
    // Server-side and on purpose in production (logger.ts is dev-only): a
    // pricing page with no plans must show up in the pod logs.
    // eslint-disable-next-line no-console
    console.error(
      `[pricing] selva_catalog_unavailable: GET ${url} failed (${
        error instanceof Error ? error.message : String(error)
      }); /pricing shows no plans`,
    );
    return null;
  }
}
