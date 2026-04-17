'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

import { VoiceModeStep } from '@/components/VoiceModeStep';
import { useVoiceMode } from '@/hooks/useVoiceMode';

export default function OnboardingPage() {
  const router = useRouter();
  const { status, loading } = useVoiceMode();

  useEffect(() => {
    if (!loading && status?.onboarding_complete) {
      router.replace('/office');
    }
  }, [loading, status, router]);

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-400">
        Loading onboarding…
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-12 text-slate-100">
      <div className="mx-auto max-w-2xl space-y-6">
        <header className="space-y-2">
          <h1 className="text-2xl font-bold">Welcome to Selva Office</h1>
          <p className="text-slate-400">
            Before agents can send anything on your behalf, choose how outbound communications
            should be attributed. You can change this later from the office.
          </p>
        </header>

        <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-6">
          <VoiceModeStep mode="onboarding" onDone={() => router.replace('/office')} />
        </section>

        <p className="text-xs text-slate-500">
          Your selection is recorded in an append-only consent ledger. Updates and deletes are
          revoked at the database level.
        </p>
      </div>
    </main>
  );
}
