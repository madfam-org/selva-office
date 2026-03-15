import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import BillingPage from '../app/billing/page';

const mockBillingStatus = {
  tier: 'Pro',
  daily_limit: 50000,
};

const mockTokenUsage = {
  used_today: 12500,
  daily_limit: 50000,
  remaining: 37500,
};

function mockBillingFetch() {
  vi.spyOn(global, 'fetch').mockImplementation((url) => {
    const urlStr = typeof url === 'string' ? url : url.toString();

    if (urlStr.includes('/api/v1/billing/status')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockBillingStatus),
      } as Response);
    }
    if (urlStr.includes('/api/v1/billing/tokens')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockTokenUsage),
      } as Response);
    }

    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({}),
    } as Response);
  });
}

describe('BillingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    vi.spyOn(global, 'fetch').mockImplementation(
      () => new Promise(() => {}),
    );

    render(<BillingPage />);
    expect(screen.getByText('Loading billing data...')).toBeInTheDocument();
  });

  it('renders the page heading', async () => {
    mockBillingFetch();
    render(<BillingPage />);

    await waitFor(() => {
      expect(screen.getByText(/Billing/)).toBeInTheDocument();
    });

    expect(
      screen.getByText('Subscription tier and compute token usage'),
    ).toBeInTheDocument();
  });

  it('displays subscription tier name', async () => {
    mockBillingFetch();
    render(<BillingPage />);

    await waitFor(() => {
      expect(screen.getByText('Pro')).toBeInTheDocument();
    });

    expect(screen.getByText('Subscription Tier')).toBeInTheDocument();
  });

  it('displays token usage with progress bar', async () => {
    mockBillingFetch();
    render(<BillingPage />);

    await waitFor(() => {
      expect(screen.getByText('Daily Token Usage')).toBeInTheDocument();
    });

    expect(screen.getByText('12,500')).toBeInTheDocument();
    expect(screen.getByText(/37,500 tokens remaining today/)).toBeInTheDocument();
  });

  it('renders the Manage Subscription link', async () => {
    mockBillingFetch();
    render(<BillingPage />);

    await waitFor(() => {
      expect(screen.getByText('Manage Subscription')).toBeInTheDocument();
    });
  });

  it('shows error message when fetch fails', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(
      new Error('Billing service down'),
    );

    render(<BillingPage />);

    await waitFor(() => {
      expect(
        screen.getByText(/Billing service down/),
      ).toBeInTheDocument();
    });
  });
});
