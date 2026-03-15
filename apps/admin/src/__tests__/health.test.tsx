import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import HealthPage from '../app/health/page';

const mockHealthData = {
  status: 'healthy',
  checks: [
    { component: 'PostgreSQL', status: 'healthy', latency_ms: 5 },
    { component: 'Redis', status: 'healthy', latency_ms: 2 },
    { component: 'Colyseus', status: 'unhealthy', latency_ms: undefined },
    { component: 'Workers', status: 'healthy', latency_ms: 12 },
  ],
};

function mockHealthFetch() {
  vi.spyOn(global, 'fetch').mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(mockHealthData),
  } as Response);
}

describe('HealthPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows loading state initially', () => {
    vi.spyOn(global, 'fetch').mockImplementation(
      () => new Promise(() => {}),
    );

    render(<HealthPage />);
    expect(
      screen.getByText('Checking system health...'),
    ).toBeInTheDocument();
  });

  it('renders the page heading', async () => {
    mockHealthFetch();
    render(<HealthPage />);

    await waitFor(() => {
      expect(screen.getByText('System Health')).toBeInTheDocument();
    });

    expect(
      screen.getByText(/auto-refreshes every 15s/),
    ).toBeInTheDocument();
  });

  it('displays health check components with status indicators', async () => {
    mockHealthFetch();
    render(<HealthPage />);

    await waitFor(() => {
      expect(screen.getByText('PostgreSQL')).toBeInTheDocument();
    });

    expect(screen.getByText('Redis')).toBeInTheDocument();
    expect(screen.getByText('Colyseus')).toBeInTheDocument();
    expect(screen.getByText('Workers')).toBeInTheDocument();
  });

  it('shows latency values for components that report them', async () => {
    mockHealthFetch();
    render(<HealthPage />);

    await waitFor(() => {
      expect(screen.getByText('5ms latency')).toBeInTheDocument();
    });

    expect(screen.getByText('2ms latency')).toBeInTheDocument();
    expect(screen.getByText('12ms latency')).toBeInTheDocument();
  });

  it('renders status text for each component', async () => {
    mockHealthFetch();
    render(<HealthPage />);

    await waitFor(() => {
      expect(screen.getByText('PostgreSQL')).toBeInTheDocument();
    });

    // 3 healthy + 1 unhealthy
    const healthyLabels = screen.getAllByText('healthy');
    expect(healthyLabels).toHaveLength(3);

    const unhealthyLabels = screen.getAllByText('unhealthy');
    expect(unhealthyLabels).toHaveLength(1);
  });

  it('shows error message when fetch fails', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(
      new Error('Server unreachable'),
    );

    render(<HealthPage />);

    await waitFor(() => {
      expect(screen.getByText(/Server unreachable/)).toBeInTheDocument();
    });
  });

  it('dismisses error when Dismiss button is clicked', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(
      new Error('Server unreachable'),
    );

    render(<HealthPage />);

    await waitFor(() => {
      expect(screen.getByText(/Server unreachable/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Dismiss'));

    expect(
      screen.queryByText(/Server unreachable/),
    ).not.toBeInTheDocument();
  });

  it('shows empty state when no checks are available', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'unknown', checks: [] }),
    } as Response);

    render(<HealthPage />);

    await waitFor(() => {
      expect(
        screen.getByText('No health checks available'),
      ).toBeInTheDocument();
    });
  });
});
