import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MetricsDashboard } from '../MetricsDashboard';

const apiFetchMock = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}));

vi.mock('@/hooks/useFocusTrap', () => ({
  useFocusTrap: () => ({ current: null }),
}));

function dashboard(overrides: Record<string, unknown> = {}) {
  return {
    period: '24h',
    agent_utilization_pct: 12.5,
    task_throughput: { status_counts: { completed: 3, failed: 1 }, total: 4, avg_duration_s: 3725.4 },
    approval_latency: { avg_seconds: 90, resolved_count: 2, pending_count: 1 },
    cost_breakdown: [
      { provider: 'provider-a', model: 'model-large', total_tokens: 2300, call_count: 2 },
      { provider: 'provider-a', model: 'model-small', total_tokens: 800, call_count: 1 },
    ],
    error_rate: 3.2,
    trends: { tasks: [], errors: [] },
    recent_errors: [],
    ...overrides,
  };
}

function ok(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

describe('MetricsDashboard', () => {
  beforeEach(() => apiFetchMock.mockReset());

  it('does not fetch while closed', () => {
    render(<MetricsDashboard open={false} onClose={() => {}} />);
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it('labels inference usage as tokens, never as cost', async () => {
    apiFetchMock.mockReturnValue(ok(dashboard()));
    render(<MetricsDashboard open onClose={() => {}} />);

    expect(await screen.findByText('Inference tokens by provider')).toBeInTheDocument();
    expect(screen.getByText('Token volume, not spend.')).toBeInTheDocument();
    expect(screen.getByText('provider-a · model-large')).toBeInTheDocument();
    expect(screen.getByText('provider-a · model-small')).toBeInTheDocument();
    expect(screen.queryByText(/cost by provider/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
    expect(screen.getByText('avg 1h 2m to finish')).toBeInTheDocument();
  });

  it('shows an unknown error rate as a dash, not 0%', async () => {
    apiFetchMock.mockReturnValue(ok(dashboard({ error_rate: null })));
    render(<MetricsDashboard open onClose={() => {}} />);

    expect(await screen.findByText('no task events in period')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.queryByText('0.0%')).not.toBeInTheDocument();
  });

  it('reports a failed load with a retry instead of "no data"', async () => {
    apiFetchMock.mockReturnValueOnce(Promise.resolve({ ok: false, status: 503 }));
    render(<MetricsDashboard open onClose={() => {}} />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't load metrics. The metrics service answered 503.");
    expect(screen.queryByText('No metrics data available')).not.toBeInTheDocument();

    apiFetchMock.mockReturnValueOnce(ok(dashboard()));
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.getByText('Inference tokens by provider')).toBeInTheDocument();
  });

  it('is a labelled dialog that closes on Escape', async () => {
    apiFetchMock.mockReturnValue(ok(dashboard()));
    const onClose = vi.fn();
    render(<MetricsDashboard open onClose={onClose} />);

    expect(screen.getByRole('dialog', { name: 'Ops Metrics' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '24h' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
    await screen.findByText('Inference tokens by provider');
  });
});
