import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useWorkflow } from '../useWorkflow';

// Mock apiFetch
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
const mockApiFetch = vi.mocked(apiFetch);

describe('useWorkflow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts with idle status', () => {
    const { result } = renderHook(() => useWorkflow());
    expect(result.current.status).toBe('idle');
    expect(result.current.error).toBeNull();
    expect(result.current.workflowList).toEqual([]);
    expect(result.current.workflow).toBeNull();
    expect(result.current.validationResult).toBeNull();
  });

  it('loadList transitions through loading to idle on success', async () => {
    const workflows = [
      { id: '1', name: 'Test', version: '1.0.0', description: '', created_at: '', updated_at: '' },
    ];
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => workflows,
    } as Response);

    const { result } = renderHook(() => useWorkflow());

    await act(async () => {
      await result.current.loadList();
    });

    expect(result.current.status).toBe('idle');
    expect(result.current.workflowList).toEqual(workflows);
  });

  it('loadList transitions to error on failure', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
    } as Response);

    const { result } = renderHook(() => useWorkflow());

    await act(async () => {
      await result.current.loadList();
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toContain('500');
  });

  it('save sends POST for new workflow', async () => {
    const saved = {
      id: '1',
      name: 'New WF',
      version: '1.0.0',
      description: '',
      yaml_content: 'name: New WF\nnodes: []\nedges: []',
      created_at: '',
      updated_at: '',
    };
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => saved,
    } as Response);

    const { result } = renderHook(() => useWorkflow());

    let returned: unknown;
    await act(async () => {
      returned = await result.current.save('New WF', 'yaml content');
    });

    expect(mockApiFetch).toHaveBeenCalledWith('/api/v1/workflows', expect.objectContaining({ method: 'POST' }));
    expect(result.current.workflow).toEqual(saved);
    expect(returned).toEqual(saved);
    expect(result.current.status).toBe('idle');
  });

  it('save sends PUT for existing workflow', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: '123', name: 'Updated' }),
    } as Response);

    const { result } = renderHook(() => useWorkflow());

    await act(async () => {
      await result.current.save('Updated', 'yaml', '123');
    });

    expect(mockApiFetch).toHaveBeenCalledWith('/api/v1/workflows/123', expect.objectContaining({ method: 'PUT' }));
  });

  it('validate sends POST and stores result', async () => {
    const validationResult = { valid: true, errors: [], warnings: [] };
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => validationResult,
    } as Response);

    const { result } = renderHook(() => useWorkflow());

    await act(async () => {
      await result.current.validate('yaml');
    });

    expect(result.current.validationResult).toEqual(validationResult);
    expect(result.current.status).toBe('idle');
  });

  it('deleteWorkflow removes from list', async () => {
    // First populate list
    const workflows = [
      { id: '1', name: 'A', version: '1.0.0', description: '', created_at: '', updated_at: '' },
      { id: '2', name: 'B', version: '1.0.0', description: '', created_at: '', updated_at: '' },
    ];
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => workflows,
    } as Response);

    const { result } = renderHook(() => useWorkflow());

    await act(async () => {
      await result.current.loadList();
    });

    expect(result.current.workflowList).toHaveLength(2);

    // Now delete
    mockApiFetch.mockResolvedValueOnce({ ok: true } as Response);

    await act(async () => {
      await result.current.deleteWorkflow('1');
    });

    expect(result.current.workflowList).toHaveLength(1);
    expect(result.current.workflowList[0].id).toBe('2');
  });
});
