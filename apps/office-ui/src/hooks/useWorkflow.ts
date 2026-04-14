'use client';

import { useState, useCallback } from 'react';
import { apiFetch } from '@/lib/api';

export interface WorkflowSummary {
  id: string;
  name: string;
  version: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface WorkflowDetail extends WorkflowSummary {
  yaml_content: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export type WorkflowStatus = 'idle' | 'loading' | 'saving' | 'validating' | 'error';

export function useWorkflow() {
  const [status, setStatus] = useState<WorkflowStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [workflowList, setWorkflowList] = useState<WorkflowSummary[]>([]);
  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);

  const loadList = useCallback(async () => {
    setStatus('loading');
    setError(null);
    try {
      const res = await apiFetch('/api/v1/workflows');
      if (!res.ok) throw new Error(`Failed to load workflows (${res.status})`);
      const data = (await res.json()) as WorkflowSummary[];
      setWorkflowList(data);
      setStatus('idle');
    } catch (err) {
      setError((err as Error).message);
      setStatus('error');
    }
  }, []);

  const load = useCallback(async (id: string) => {
    setStatus('loading');
    setError(null);
    try {
      const res = await apiFetch(`/api/v1/workflows/${id}`);
      if (!res.ok) throw new Error(`Failed to load workflow (${res.status})`);
      const data = (await res.json()) as WorkflowDetail;
      setWorkflow(data);
      setStatus('idle');
      return data;
    } catch (err) {
      setError((err as Error).message);
      setStatus('error');
      return null;
    }
  }, []);

  const save = useCallback(async (name: string, yamlContent: string, id?: string) => {
    setStatus('saving');
    setError(null);
    try {
      const url = id ? `/api/v1/workflows/${id}` : '/api/v1/workflows';
      const method = id ? 'PUT' : 'POST';
      const res = await apiFetch(url, {
        method,
        body: JSON.stringify({ name, yaml_content: yamlContent }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as Record<string, string>).detail ?? `Save failed (${res.status})`);
      }
      const data = (await res.json()) as WorkflowDetail;
      setWorkflow(data);
      setStatus('idle');
      return data;
    } catch (err) {
      setError((err as Error).message);
      setStatus('error');
      return null;
    }
  }, []);

  const validate = useCallback(async (yamlContent: string) => {
    setStatus('validating');
    setError(null);
    try {
      const res = await apiFetch('/api/v1/workflows/validate', {
        method: 'POST',
        body: JSON.stringify({ yaml_content: yamlContent }),
      });
      if (!res.ok) throw new Error(`Validation request failed (${res.status})`);
      const data = (await res.json()) as ValidationResult;
      setValidationResult(data);
      setStatus('idle');
      return data;
    } catch (err) {
      setError((err as Error).message);
      setStatus('error');
      return null;
    }
  }, []);

  const deleteWorkflow = useCallback(async (id: string) => {
    setStatus('loading');
    setError(null);
    try {
      const res = await apiFetch(`/api/v1/workflows/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`Delete failed (${res.status})`);
      setWorkflowList((prev) => prev.filter((w) => w.id !== id));
      if (workflow?.id === id) setWorkflow(null);
      setStatus('idle');
    } catch (err) {
      setError((err as Error).message);
      setStatus('error');
    }
  }, [workflow?.id]);

  const importYaml = useCallback(async (yamlContent: string) => {
    setStatus('saving');
    setError(null);
    try {
      const res = await apiFetch('/api/v1/workflows/import', {
        method: 'POST',
        body: JSON.stringify({ yaml_content: yamlContent }),
      });
      if (!res.ok) throw new Error(`Import failed (${res.status})`);
      const data = (await res.json()) as WorkflowDetail;
      setWorkflow(data);
      setStatus('idle');
      return data;
    } catch (err) {
      setError((err as Error).message);
      setStatus('error');
      return null;
    }
  }, []);

  const exportYaml = useCallback(async (id: string): Promise<string | null> => {
    setStatus('loading');
    setError(null);
    try {
      const res = await apiFetch(`/api/v1/workflows/${id}/export`);
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const data = (await res.json()) as { yaml_content: string };
      setStatus('idle');
      return data.yaml_content;
    } catch (err) {
      setError((err as Error).message);
      setStatus('error');
      return null;
    }
  }, []);

  return {
    status,
    error,
    workflowList,
    workflow,
    validationResult,
    loadList,
    load,
    save,
    validate,
    deleteWorkflow,
    importYaml,
    exportYaml,
  };
}
