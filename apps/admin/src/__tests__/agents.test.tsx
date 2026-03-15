import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AgentsPage from '../app/agents/page';

const mockAgents = [
  {
    id: 'a1',
    name: 'ByteForge',
    role: 'coder' as const,
    status: 'idle' as const,
    departmentId: 'd1',
    level: 3,
    skill_ids: [],
  },
  {
    id: 'a2',
    name: 'DeepDive',
    role: 'researcher' as const,
    status: 'working' as const,
    departmentId: 'd2',
    level: 5,
    skill_ids: [],
  },
];

const mockDepartments = [
  { id: 'd1', name: 'Engineering', slug: 'engineering' },
  { id: 'd2', name: 'Research', slug: 'research' },
];

function mockFetchForAgents() {
  vi.spyOn(global, 'fetch').mockImplementation((url) => {
    const urlStr = typeof url === 'string' ? url : url.toString();

    if (urlStr.includes('/api/v1/departments')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockDepartments),
      } as Response);
    }
    if (urlStr.includes('/api/v1/agents')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockAgents),
      } as Response);
    }

    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve([]),
    } as Response);
  });
}

describe('AgentsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    vi.spyOn(global, 'fetch').mockImplementation(
      () => new Promise(() => {}),
    );

    render(<AgentsPage />);
    expect(screen.getByText('Loading agents...')).toBeInTheDocument();
  });

  it('renders the page heading and navigation', async () => {
    mockFetchForAgents();
    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText('Agent Management')).toBeInTheDocument();
    });

    expect(
      screen.getByText('View, edit, and manage all AI agents'),
    ).toBeInTheDocument();
  });

  it('renders agent table with correct columns', async () => {
    mockFetchForAgents();
    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText('ByteForge')).toBeInTheDocument();
    });

    // Table header columns
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(screen.getByText('Role')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Department')).toBeInTheDocument();
    expect(screen.getByText('Level')).toBeInTheDocument();
    expect(screen.getByText('Actions')).toBeInTheDocument();
  });

  it('displays agent data in the table', async () => {
    mockFetchForAgents();
    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText('ByteForge')).toBeInTheDocument();
    });

    expect(screen.getByText('DeepDive')).toBeInTheDocument();
    expect(screen.getByText('coder')).toBeInTheDocument();
    expect(screen.getByText('researcher')).toBeInTheDocument();
    expect(screen.getByText('Engineering')).toBeInTheDocument();
    expect(screen.getByText('Research')).toBeInTheDocument();
  });

  it('shows empty state when no agents exist', async () => {
    vi.spyOn(global, 'fetch').mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      } as Response),
    );

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText('No agents found')).toBeInTheDocument();
    });
  });

  it('shows delete confirmation when Delete button is clicked', async () => {
    mockFetchForAgents();
    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText('ByteForge')).toBeInTheDocument();
    });

    // Click the first Delete button
    const deleteButtons = screen.getAllByText('Delete');
    fireEvent.click(deleteButtons[0]);

    // Confirm and Cancel buttons should appear
    expect(screen.getByText('Confirm')).toBeInTheDocument();
    expect(screen.getAllByText('Cancel').length).toBeGreaterThan(0);
  });

  it('calls DELETE API when delete is confirmed', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    mockFetchForAgents();
    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText('ByteForge')).toBeInTheDocument();
    });

    // Click Delete on first agent
    const deleteButtons = screen.getAllByText('Delete');
    fireEvent.click(deleteButtons[0]);

    // Override fetch for the DELETE call
    fetchSpy.mockImplementation((url, opts) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      if (
        urlStr.includes('/api/v1/agents/a1') &&
        opts &&
        (opts as RequestInit).method === 'DELETE'
      ) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
      }
      // Return agents/departments for refetch
      if (urlStr.includes('/api/v1/departments')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockDepartments),
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockAgents),
      } as Response);
    });

    // Click Confirm
    fireEvent.click(screen.getByText('Confirm'));

    await waitFor(() => {
      // The agent should be removed from the list
      expect(screen.queryByText('ByteForge')).not.toBeInTheDocument();
    });
  });

  it('shows Reassign controls when Reassign button is clicked', async () => {
    mockFetchForAgents();
    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText('ByteForge')).toBeInTheDocument();
    });

    const reassignButtons = screen.getAllByText('Reassign');
    fireEvent.click(reassignButtons[0]);

    // A select dropdown and Save/Cancel should appear
    expect(screen.getByText('Save')).toBeInTheDocument();
    expect(screen.getAllByText('Cancel').length).toBeGreaterThan(0);
  });

  it('shows error when fetch fails', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(
      new Error('Connection refused'),
    );

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText(/Connection refused/)).toBeInTheDocument();
    });
  });

  it('dismisses error when Dismiss button is clicked', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(
      new Error('Connection refused'),
    );

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText(/Connection refused/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Dismiss'));

    expect(screen.queryByText(/Connection refused/)).not.toBeInTheDocument();
  });
});
