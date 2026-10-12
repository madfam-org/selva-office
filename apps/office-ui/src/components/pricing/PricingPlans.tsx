'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { getSessionToken } from '@/lib/api';
import type { SelvaPlan } from '@/lib/selva-catalog';
import { useCheckout } from '@/hooks/useCheckout';
import { ToastProvider } from '@/components/Toast';
import { ThemeToggle } from '@/components/ThemeToggle';

const MXN = new Intl.NumberFormat('es-MX', {
  style: 'currency',
  currency: 'MXN',
  maximumFractionDigits: 0,
});

interface PricingPlansProps {
  /** Plans from the Dhanam catalog, or null when the catalog could not be read. */
  plans: SelvaPlan[] | null;
}

function PlansInner({ plans }: PricingPlansProps) {
  const { loading, startCheckout } = useCheckout();
  const [pendingTier, setPendingTier] = useState<string | null>(null);
  // Read after mount: the session cookie is not visible to the server render.
  const [signedIn, setSignedIn] = useState(true);
  useEffect(() => {
    setSignedIn(getSessionToken() !== null);
  }, []);

  const choose = useCallback(
    (slug: string) => {
      setPendingTier(slug);
      void startCheckout(slug);
    },
    [startCheckout],
  );

  return (
    <main className="min-h-screen bg-surface px-4 py-16">
      <div className="fixed left-4 top-4">
        <ThemeToggle />
      </div>

      <div className="mx-auto max-w-4xl">
        <header className="mb-12 text-center">
          <h1 className="text-3xl font-semibold text-ink">Choose your plan</h1>
          <p className="mt-2 text-sm text-ink-muted">
            Every plan sets your daily compute budget. Upgrade any time — your
            agents keep working.
          </p>
          {!signedIn && (
            <p className="mt-3 text-sm text-ink-muted">
              <Link
                href="/login?redirect=/pricing"
                className="font-medium text-accent hover:underline"
              >
                Sign in
              </Link>{' '}
              to choose a plan.
            </p>
          )}
        </header>

        {!plans && (
          <p className="text-center text-sm text-ink-muted">
            Couldn&apos;t load plans right now. Please refresh.
          </p>
        )}

        {plans && (
          <div className="grid gap-6 md:grid-cols-3">
            {plans.map((plan) => (
              <div
                key={plan.slug}
                data-testid={`plan-${plan.slug}`}
                className="flex flex-col rounded-2xl border border-edge bg-surface-raised p-6"
              >
                <h2 className="text-lg font-semibold text-ink">{plan.name}</h2>
                <p className="mt-4 text-3xl font-semibold text-accent">
                  {MXN.format(plan.mxnMonthlyGross)}
                  <span className="ml-1 text-sm font-normal text-ink-muted">
                    MXN / month
                  </span>
                </p>
                <p className="mt-1 text-xs text-ink-muted">IVA incluido</p>
                {plan.dailyTokenLimit !== null && (
                  <p className="mt-4 text-sm text-ink">
                    {plan.dailyTokenLimit.toLocaleString('en-US')} compute tokens / day
                  </p>
                )}
                {plan.features.length > 0 && (
                  <ul className="mt-3 flex-1 space-y-1 text-xs text-ink-muted">
                    {plan.features.map((feature) => (
                      <li key={feature}>{feature}</li>
                    ))}
                  </ul>
                )}
                <button
                  type="button"
                  onClick={() => choose(plan.slug)}
                  disabled={loading}
                  className="mt-6 w-full rounded-full bg-accent px-4 py-2.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {loading && pendingTier === plan.slug
                    ? 'Starting checkout…'
                    : 'Choose'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

/**
 * The /pricing grid. Prices come from the Dhanam catalog (see
 * src/lib/selva-catalog.ts); each "Choose" starts the signed-in checkout
 * through nexus-api (`POST /api/v1/billing/checkout`) with the catalog tier
 * slug, which nexus-api validates against the same catalog.
 */
export function PricingPlans({ plans }: PricingPlansProps) {
  return (
    <ToastProvider>
      <PlansInner plans={plans} />
    </ToastProvider>
  );
}
