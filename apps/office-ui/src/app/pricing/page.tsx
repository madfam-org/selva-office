import type { Metadata } from 'next';
import { PricingPlans } from '@/components/pricing/PricingPlans';
import { fetchSelvaPlans } from '@/lib/selva-catalog';

/**
 * /pricing — Selva's subscription plans, public.
 *
 * Plans and prices come from Dhanam's public catalog
 * (`GET /v1/billing/catalog/selva`), read on the server: anonymous visitors
 * see them, and the HTML carries them. The page used to call nexus-api's
 * `/api/v1/billing/tiers`, which requires a session, so every anonymous
 * visitor got «Couldn't load plans» (J2, money-engine journeys 2026-10-11).
 *
 * Rendered per request; the catalog read itself is cached for five minutes
 * (CATALOG_REVALIDATE_SECONDS), so builds never depend on reaching Dhanam.
 */
export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'Selva — Pricing',
  description:
    'Selva plans: Developer, Team and Business. Monthly MXN prices with IVA included, from the MADFAM catalog.',
};

export default async function PricingPage() {
  const plans = await fetchSelvaPlans();
  return <PricingPlans plans={plans} />;
}
