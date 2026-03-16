import type { Metadata } from 'next';
import { HeroSection } from '@/components/landing/HeroSection';
import { FeatureGrid } from '@/components/landing/FeatureGrid';
import { HowItWorks } from '@/components/landing/HowItWorks';
import { Footer } from '@/components/landing/Footer';

export const metadata: Metadata = {
  title: 'AutoSwarm Office — AI Agents in a Virtual Office',
  description:
    'Dispatch tasks to AI agents, watch them collaborate in real-time, and approve every action. Try the demo now.',
};

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-slate-950 scanline-overlay">
      <HeroSection />
      <FeatureGrid />
      <HowItWorks />
      <Footer />
    </div>
  );
}
