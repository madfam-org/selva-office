import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useWorkflowTemplates } from '../useWorkflowTemplates';

// Mock apiFetch
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
const mockApiFetch = vi.mocked(apiFetch);

describe('useWorkflowTemplates', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts with idle status and empty templates', () => {
    const { result } = renderHook(() => useWorkflowTemplates());
    expect(result.current.status).toBe('idle');
    expect(result.current.error).toBeNull();
    expect(result.current.templates).toEqual([]);
  });

  it('fetchTemplates loads templates on success', async () => {
    const templates = [
      { name: 'Pipeline', description: 'desc', filename: 'pipe.yaml', category: 'Dev', node_count: 3 },
    ];
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => templates,
    } as Response);

    const { result } = renderHook(() => useWorkflowTemplates());

    await act(async () => {
      await result.current.fetchTemplates();
    });

    expect(result.current.status).toBe('idle');
    expect(result.current.templates).toEqual(templates);
    expect(mockApiFetch).toHaveBeenCalledWith('/api/v1/workflows/templates');
  });

  it('fetchTemplates transitions to error on failure', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
    } as Response);

    const { result } = renderHook(() => useWorkflowTemplates());

    await act(async () => {
      await result.current.fetchTemplates();
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toContain('500');
  });

  it('createFromTemplate sends POST and returns workflow', async () => {
    const created = {
      id: '1',
      name: 'Created WF',
      version: '1.0.0',
      description: 'desc',
      yaml_content: 'name: test\nnodes: []',
      org_id: 'org',
      created_at: '',
      updated_at: '',
    };
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => created,
    } as Response);

    const { result } = renderHook(() => useWorkflowTemplates());

    let returned: unknown;
    await act(async () => {
      returned = await result.current.createFromTemplate('pipe.yaml', 'Custom Name');
    });

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/workflows/from-template',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(returned).toEqual(created);
    expect(result.current.status).toBe('idle');
  });

  it('createFromTemplate returns null on error', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Template not found' }),
    } as Response);

    const { result } = renderHook(() => useWorkflowTemplates());

    let returned: unknown;
    await act(async () => {
      returned = await result.current.createFromTemplate('missing.yaml');
    });

    expect(returned).toBeNull();
    expect(result.current.status).toBe('error');
    expect(result.current.error).toContain('Template not found');
  });
});
