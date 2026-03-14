import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { CalendarPanel } from '../CalendarPanel';
import type { CalendarEvent, CalendarStatus } from '../../hooks/useCalendar';

// Mock gameEventBus to avoid Phaser dependency
vi.mock('../../game/PhaserGame', () => ({
  gameEventBus: {
    emit: vi.fn(),
    on: vi.fn(() => vi.fn()),
  },
}));

function renderPanel(overrides: Partial<React.ComponentProps<typeof CalendarPanel>> = {}) {
  const defaults = {
    open: true,
    onClose: vi.fn(),
    events: [] as CalendarEvent[],
    isBusy: false,
    connected: false,
    status: 'idle' as CalendarStatus,
    error: null,
    onConnect: vi.fn().mockResolvedValue(true),
    onDisconnect: vi.fn().mockResolvedValue(true),
    onRefresh: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  return { ...render(<CalendarPanel {...defaults} />), props: defaults };
}

describe('CalendarPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders when open', () => {
    renderPanel();
    expect(screen.getByText('Calendar')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    renderPanel({ open: false });
    expect(screen.queryByText('Calendar')).not.toBeInTheDocument();
  });

  it('shows connect form when not connected', () => {
    renderPanel({ connected: false });
    expect(screen.getByText('Connect Calendar')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('OAuth2 access token...')).toBeInTheDocument();
    expect(screen.getByText('google')).toBeInTheDocument();
    expect(screen.getByText('microsoft')).toBeInTheDocument();
  });

  it('shows disconnect button when connected', () => {
    renderPanel({ connected: true });
    expect(screen.getByText('Disconnect Calendar')).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
  });

  it('shows events when connected with events', () => {
    const events: CalendarEvent[] = [
      {
        id: 'evt-1',
        title: 'Team Standup',
        start: '2026-03-14T10:00:00Z',
        end: '2026-03-14T10:30:00Z',
        is_all_day: false,
        meeting_url: 'https://meet.google.com/abc',
        organizer: 'boss@example.com',
        attendees: [],
        provider: 'google',
      },
    ];
    renderPanel({ connected: true, events });
    expect(screen.getByText('Team Standup')).toBeInTheDocument();
    expect(screen.getByText('Join Meeting')).toBeInTheDocument();
    expect(screen.getByText('boss@example.com')).toBeInTheDocument();
  });

  it('shows "No upcoming events" when connected with empty events', () => {
    renderPanel({ connected: true, events: [] });
    expect(screen.getByText('No upcoming events')).toBeInTheDocument();
  });

  it('shows "In Meeting" badge when busy', () => {
    renderPanel({ connected: true, isBusy: true });
    expect(screen.getByText('In Meeting')).toBeInTheDocument();
  });

  it('disables connect button when token is empty', () => {
    renderPanel({ connected: false });
    const connectBtn = screen.getByText('Connect Calendar');
    expect(connectBtn).toBeDisabled();
  });

  it('calls onConnect with form values', async () => {
    const onConnect = vi.fn().mockResolvedValue(true);
    renderPanel({ connected: false, onConnect });

    const tokenInput = screen.getByPlaceholderText('OAuth2 access token...');
    fireEvent.change(tokenInput, { target: { value: 'test-token' } });

    // Select microsoft provider
    const msBtn = screen.getByText('microsoft');
    fireEvent.click(msBtn);

    const connectBtn = screen.getByText('Connect Calendar');
    fireEvent.click(connectBtn);

    await waitFor(() => {
      expect(onConnect).toHaveBeenCalledWith('microsoft', 'test-token', undefined);
    });
  });

  it('calls onDisconnect when disconnect button clicked', async () => {
    const onDisconnect = vi.fn().mockResolvedValue(true);
    renderPanel({ connected: true, onDisconnect });

    const disconnectBtn = screen.getByText('Disconnect Calendar');
    fireEvent.click(disconnectBtn);

    await waitFor(() => {
      expect(onDisconnect).toHaveBeenCalled();
    });
  });

  it('calls onClose when ESC button clicked', () => {
    const { props } = renderPanel();
    const escBtn = screen.getByLabelText('Close calendar panel');
    fireEvent.click(escBtn);
    expect(props.onClose).toHaveBeenCalled();
  });

  it('shows "Connecting..." when status is connecting', () => {
    renderPanel({ connected: false, status: 'connecting' });
    // Fill token so the button shows connecting state
    const tokenInput = screen.getByPlaceholderText('OAuth2 access token...');
    fireEvent.change(tokenInput, { target: { value: 'test' } });
    expect(screen.getByText('Connecting...')).toBeInTheDocument();
  });

  it('renders meeting url as link', () => {
    const events: CalendarEvent[] = [
      {
        id: 'evt-link',
        title: 'Video Call',
        start: '2026-03-14T14:00:00Z',
        end: '2026-03-14T15:00:00Z',
        is_all_day: false,
        meeting_url: 'https://teams.microsoft.com/xyz',
        organizer: '',
        attendees: [],
        provider: 'microsoft',
      },
    ];
    renderPanel({ connected: true, events });
    const link = screen.getByText('Join Meeting');
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', 'https://teams.microsoft.com/xyz');
    expect(link).toHaveAttribute('target', '_blank');
  });
});
