import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import PricingPage from '../page';
import { mxnGrossFromNetCentavos, selvaPlansFromCatalog } from '@/lib/selva-catalog';

const apiFetchMock = vi.fn();
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetchMock(...args) };
});

const addToastMock = vi.fn();
vi.mock('@/hooks/useToast', async () => {
  const actual = await vi.importActual<typeof import('@/hooks/useToast')>(
    '@/hooks/useToast',
  );
  return { ...actual, useToast: () => ({ toasts: [], addToast: addToastMock, removeToast: vi.fn() }) };
});

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

// Shape of GET https://api.dhan.am/v1/billing/catalog/selva. The amounts are
// test data: expectations below derive from them through the IVA rule, the
// way the page does, rather than restating any price.
const CATALOG_PRODUCT = {
  slug: 'selva',
  name: 'Selva',
  tiers: [
    {
      tierSlug: 'developer',
      name: 'Developer',
      displayName: 'Developer',
      metadata: { max_agents: 2, daily_token_limit: 200 },
      prices: { USD: { monthly: 4900, yearly: null }, MXN: { monthly: 99900, yearly: null } },
      features: ['2 concurrent agents', '200 compute tokens/day'],
    },
    {
      tierSlug: 'team',
      name: 'Team',
      displayName: 'Team',
      metadata: { max_agents: 5, daily_token_limit: 1000 },
      prices: { USD: { monthly: 14900, yearly: null }, MXN: { monthly: 299900, yearly: null } },
      features: ['5 concurrent agents', '1,000 compute tokens/day'],
    },
    {
      tierSlug: 'business',
      name: 'Business',
      displayName: 'Business',
      metadata: { max_agents: 20, daily_token_limit: 10000 },
      prices: { USD: { monthly: 49900, yearly: null }, MXN: { monthly: 999900, yearly: null } },
      features: ['20 concurrent agents', '10,000 compute tokens/day'],
    },
  ],
};

const mxn = (pesos: number) =>
  new Intl.NumberFormat('es-MX', {
    style: 'currency',
    currency: 'MXN',
    maximumFractionDigits: 0,
  }).format(pesos);

const fetchMock = vi.fn();

describe('selva catalog helpers', () => {
  it('applies the IVA ceil rule on whole pesos, as Dhanam does', () => {
    // net 999.00 × 1.16 = 1158.84 → 1159 (rounded UP, never to nearest)
    expect(mxnGrossFromNetCentavos(99900)).toBe(1159);
    expect(mxnGrossFromNetCentavos(100)).toBe(2); // 1.16 → 2
    expect(mxnGrossFromNetCentavos(2500)).toBe(29); // 29.00 exactly stays 29
  });

  it('maps every catalog tier with a monthly MXN price, in catalog order', () => {
    const plans = selvaPlansFromCatalog(CATALOG_PRODUCT);
    expect(plans.map((p) => p.slug)).toEqual(['developer', 'team', 'business']);
    expect(plans[1]).toMatchObject({
      name: 'Team',
      mxnMonthlyGross: mxnGrossFromNetCentavos(299900),
      dailyTokenLimit: 1000,
      maxAgents: 5,
    });
  });

  it('skips unpriced tiers and refuses a catalog with none priced', () => {
    const unpriced = { tierSlug: 'free', name: 'Free', prices: { MXN: { monthly: null } } };
    const plans = selvaPlansFromCatalog({ tiers: [unpriced, ...CATALOG_PRODUCT.tiers] });
    expect(plans).toHaveLength(3);
    expect(() => selvaPlansFromCatalog({ tiers: [unpriced] })).toThrow();
    expect(() => selvaPlansFromCatalog({})).toThrow();
  });
});

describe('PricingPage', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    addToastMock.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the catalog plans with IVA-inclusive MXN prices, no session needed', async () => {
    fetchMock.mockResolvedValueOnce(json(CATALOG_PRODUCT));
    render(await PricingPage());

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.dhan.am/v1/billing/catalog/selva',
      expect.anything(),
    );
    // The anonymous path never touches nexus-api (whose /billing/tiers is 401).
    expect(apiFetchMock).not.toHaveBeenCalled();

    for (const tier of CATALOG_PRODUCT.tiers) {
      const card = screen.getByTestId(`plan-${tier.tierSlug}`);
      expect(card).toHaveTextContent(tier.name);
      expect(card).toHaveTextContent(mxn(mxnGrossFromNetCentavos(tier.prices.MXN.monthly)));
      expect(card).toHaveTextContent('IVA incluido');
    }
    expect(screen.getAllByRole('button', { name: /choose/i })).toHaveLength(3);
    expect(screen.queryByText(/couldn.t load plans/i)).not.toBeInTheDocument();
  });

  it('shows the error state, not invented prices, when the catalog is unreachable', async () => {
    fetchMock.mockResolvedValueOnce(json({}, 503));
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(await PricingPage());
    expect(screen.getByText(/couldn.t load plans/i)).toBeInTheDocument();
    expect(screen.queryAllByRole('button', { name: /choose/i })).toHaveLength(0);
    expect(consoleError).toHaveBeenCalledWith(
      expect.stringContaining('selva_catalog_unavailable'),
    );
  });

  it('starts the signed-in checkout with the catalog tier slug', async () => {
    fetchMock.mockResolvedValueOnce(json(CATALOG_PRODUCT));
    apiFetchMock.mockResolvedValueOnce(
      json({ detail: { status: 'not_configured' } }, 501), // /billing/checkout
    );
    render(await PricingPage());

    fireEvent.click(screen.getAllByRole('button', { name: /choose/i })[1]); // Team

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith(
        '/api/v1/billing/checkout',
        expect.objectContaining({ method: 'POST', body: JSON.stringify({ tier: 'team' }) }),
      );
      expect(addToastMock).toHaveBeenCalledWith(
        expect.stringMatching(/coming soon/i),
        'info',
      );
    });
  });

  it('asks an anonymous visitor to sign in when checkout answers 401', async () => {
    fetchMock.mockResolvedValueOnce(json(CATALOG_PRODUCT));
    apiFetchMock.mockResolvedValueOnce(json({ detail: 'Not authenticated' }, 401));
    render(await PricingPage());

    expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute(
      'href',
      '/login?redirect=/pricing',
    );
    fireEvent.click(screen.getAllByRole('button', { name: /choose/i })[0]);

    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('Sign in to choose a plan.', 'info');
    });
  });
});
