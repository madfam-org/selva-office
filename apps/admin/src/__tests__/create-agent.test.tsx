import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CreateAgentPage from '../app/agents/create/page';

const mockDepartments = [
  { id: 'd1', name: 'Engineering', slug: 'engineering' },
  { id: 'd2', name: 'Research', slug: 'research' },
];

function mockDepartmentFetch() {
  vi.spyOn(global, 'fetch').mockImplementation((url) => {
    const urlStr = typeof url === 'string' ? url : url.toString();

    if (urlStr.includes('/api/v1/departments')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockDepartments),
      } as Response);
    }

    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({}),
    } as Response);
  });
}

describe('CreateAgentPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the page heading and description', async () => {
    mockDepartmentFetch();
    render(<CreateAgentPage />);

    // "Create Agent" appears in both the heading and the submit button
    const headings = screen.getAllByText('Create Agent');
    expect(headings.length).toBeGreaterThanOrEqual(1);

    expect(
      screen.getByText('Add a new AI agent to the office'),
    ).toBeInTheDocument();
  });

  it('renders the form with name, role, and department fields', async () => {
    mockDepartmentFetch();
    render(<CreateAgentPage />);

    expect(screen.getByLabelText('Name')).toBeInTheDocument();
    expect(screen.getByLabelText('Role')).toBeInTheDocument();
    expect(screen.getByLabelText('Department')).toBeInTheDocument();
  });

  it('renders all agent role options in the select', async () => {
    mockDepartmentFetch();
    render(<CreateAgentPage />);

    const roleSelect = screen.getByLabelText('Role') as HTMLSelectElement;
    expect(roleSelect).toBeInTheDocument();

    const options = Array.from(roleSelect.querySelectorAll('option'));
    const roleValues = options.map((o) => o.value);

    expect(roleValues).toContain('planner');
    expect(roleValues).toContain('coder');
    expect(roleValues).toContain('reviewer');
    expect(roleValues).toContain('researcher');
    expect(roleValues).toContain('crm');
    expect(roleValues).toContain('support');
  });

  it('populates department dropdown from API', async () => {
    mockDepartmentFetch();
    render(<CreateAgentPage />);

    await waitFor(() => {
      const deptSelect = screen.getByLabelText('Department') as HTMLSelectElement;
      const options = Array.from(deptSelect.querySelectorAll('option'));
      const optionTexts = options.map((o) => o.textContent);
      expect(optionTexts).toContain('Engineering');
      expect(optionTexts).toContain('Research');
    });

    // Unassigned should always be present as default option
    const deptSelect = screen.getByLabelText('Department') as HTMLSelectElement;
    const options = Array.from(deptSelect.querySelectorAll('option'));
    expect(options[0].textContent).toBe('Unassigned');
  });

  it('submits the form and shows success message', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');

    // First call: department fetch
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDepartments),
    } as Response);

    render(<CreateAgentPage />);

    // Fill in the form
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'TestBot' },
    });
    fireEvent.change(screen.getByLabelText('Role'), {
      target: { value: 'researcher' },
    });

    // Mock the POST response
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          id: 'new-1',
          name: 'TestBot',
          role: 'researcher',
        }),
    } as Response);

    // Submit the form by clicking the submit button
    const submitBtn = screen.getByRole('button', { name: /Create Agent/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText('Agent created successfully!'),
      ).toBeInTheDocument();
    });
  });

  it('shows error when form submission fails', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');

    // Department fetch
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDepartments),
    } as Response);

    render(<CreateAgentPage />);

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'BadBot' },
    });

    // Mock a failed POST
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: 'Agent name already exists' }),
    } as Response);

    const submitBtn = screen.getByRole('button', { name: /Create Agent/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/Agent name already exists/),
      ).toBeInTheDocument();
    });
  });
});
