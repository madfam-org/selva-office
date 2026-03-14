'use client';

import { useState, useCallback } from 'react';
import { apiFetch } from '@/lib/api';

export interface MarketplaceEntry {
  id: string;
  name: string;
  description: string;
  author: string;
  version: string;
  category: string | null;
  tags: string[];
  downloads: number;
  avg_rating: number | null;
  created_at: string;
  updated_at: string;
}

export interface MarketplaceEntryDetail extends MarketplaceEntry {
  yaml_content: string;
  readme: string | null;
  ratings: Array<{ user_id: string; rating: number; review: string | null }>;
}

export interface PublishSkillRequest {
  name: string;
  description: string;
  yaml_content: string;
  readme?: string;
  category?: string;
  tags?: string[];
}

export type MarketplaceSortBy = 'downloads' | 'rating' | 'newest';

export type MarketplaceStatus = 'idle' | 'loading' | 'submitting' | 'error';

export function useMarketplace() {
  const [entries, setEntries] = useState<MarketplaceEntry[]>([]);
  const [entryDetail, setEntryDetail] = useState<MarketplaceEntryDetail | null>(null);
  const [status, setStatus] = useState<MarketplaceStatus>('idle');
  const [error, setError] = useState<string | null>(null);

  const fetchEntries = useCallback(
    async (search?: string, category?: string, sortBy?: MarketplaceSortBy) => {
      setStatus('loading');
      setError(null);
      try {
        const params = new URLSearchParams();
        if (search) params.set('search', search);
        if (category) params.set('category', category);
        if (sortBy) params.set('sort_by', sortBy);
        const qs = params.toString();
        const url = `/api/v1/marketplace/skills${qs ? `?${qs}` : ''}`;
        const res = await apiFetch(url);
        if (!res.ok) throw new Error(`Failed to load skills (${res.status})`);
        const data = (await res.json()) as MarketplaceEntry[];
        setEntries(data);
        setStatus('idle');
      } catch (e) {
        setError((e as Error).message);
        setStatus('error');
      }
    },
    [],
  );

  const fetchEntry = useCallback(async (id: string) => {
    setStatus('loading');
    setError(null);
    try {
      const res = await apiFetch(`/api/v1/marketplace/skills/${id}`);
      if (!res.ok) throw new Error(`Failed to load skill detail (${res.status})`);
      const data = (await res.json()) as MarketplaceEntryDetail;
      setEntryDetail(data);
      setStatus('idle');
      return data;
    } catch (e) {
      setError((e as Error).message);
      setStatus('error');
      return null;
    }
  }, []);

  const publishSkill = useCallback(async (data: PublishSkillRequest) => {
    setStatus('submitting');
    setError(null);
    try {
      const res = await apiFetch('/api/v1/marketplace/skills', {
        method: 'POST',
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(
          (body as Record<string, string>).detail ?? `Publish failed (${res.status})`,
        );
      }
      const entry = (await res.json()) as MarketplaceEntry;
      setEntries((prev) => [entry, ...prev]);
      setStatus('idle');
      return entry;
    } catch (e) {
      setError((e as Error).message);
      setStatus('error');
      return null;
    }
  }, []);

  const rateSkill = useCallback(
    async (id: string, rating: number, review?: string) => {
      setStatus('submitting');
      setError(null);
      try {
        const res = await apiFetch(`/api/v1/marketplace/skills/${id}/rate`, {
          method: 'POST',
          body: JSON.stringify({ rating, review: review ?? null }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(
            (body as Record<string, string>).detail ?? `Rating failed (${res.status})`,
          );
        }
        setStatus('idle');
        return true;
      } catch (e) {
        setError((e as Error).message);
        setStatus('error');
        return false;
      }
    },
    [],
  );

  const installSkill = useCallback(async (id: string) => {
    setStatus('submitting');
    setError(null);
    try {
      const res = await apiFetch(`/api/v1/marketplace/skills/${id}/install`, {
        method: 'POST',
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(
          (body as Record<string, string>).detail ?? `Install failed (${res.status})`,
        );
      }
      // Update download count in local state
      setEntries((prev) =>
        prev.map((e) => (e.id === id ? { ...e, downloads: e.downloads + 1 } : e)),
      );
      setStatus('idle');
      return true;
    } catch (e) {
      setError((e as Error).message);
      setStatus('error');
      return false;
    }
  }, []);

  const deleteSkill = useCallback(
    async (id: string) => {
      setStatus('submitting');
      setError(null);
      try {
        const res = await apiFetch(`/api/v1/marketplace/skills/${id}`, {
          method: 'DELETE',
        });
        if (!res.ok) throw new Error(`Delete failed (${res.status})`);
        setEntries((prev) => prev.filter((e) => e.id !== id));
        if (entryDetail?.id === id) setEntryDetail(null);
        setStatus('idle');
        return true;
      } catch (e) {
        setError((e as Error).message);
        setStatus('error');
        return false;
      }
    },
    [entryDetail?.id],
  );

  const clearDetail = useCallback(() => {
    setEntryDetail(null);
  }, []);

  return {
    entries,
    entryDetail,
    status,
    error,
    fetchEntries,
    fetchEntry,
    publishSkill,
    rateSkill,
    installSkill,
    deleteSkill,
    clearDetail,
  };
}
