'use client';

import { useState, useCallback } from 'react';
import { apiFetch } from '@/lib/api';
import type { WorkflowDetail } from '@/hooks/useWorkflow';

export interface WorkflowTemplate {
  name: string;
  description: string;
  filename: string;
  category: string;
  node_count: number;
}

export type TemplateStatus = 'idle' | 'loading' | 'creating' | 'error';

export function useWorkflowTemplates() {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [status, setStatus] = useState<TemplateStatus>('idle');
  const [error, setError] = useState<string | null>(null);

  const fetchTemplates = useCallback(async () => {
    setStatus('loading');
    setError(null);
    try {
      const res = await apiFetch('/api/v1/workflows/templates');
      if (!res.ok) throw new Error(`Failed to load templates (${res.status})`);
      const data = (await res.json()) as WorkflowTemplate[];
      setTemplates(data);
      setStatus('idle');
    } catch (e) {
      setError((e as Error).message);
      setStatus('error');
    }
  }, []);

  const createFromTemplate = useCallback(
    async (filename: string, name?: string): Promise<WorkflowDetail | null> => {
      setStatus('creating');
      setError(null);
      try {
        const body: Record<string, string> = { template_filename: filename };
        if (name) body.name = name;
        const res = await apiFetch('/api/v1/workflows/from-template', {
          method: 'POST',
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const detail = await res.json().catch(() => ({}));
          throw new Error(
            (detail as Record<string, string>).detail ?? `Create failed (${res.status})`,
          );
        }
        const data = (await res.json()) as WorkflowDetail;
        setStatus('idle');
        return data;
      } catch (e) {
        setError((e as Error).message);
        setStatus('error');
        return null;
      }
    },
    [],
  );

  return {
    templates,
    status,
    error,
    fetchTemplates,
    createFromTemplate,
  };
}
