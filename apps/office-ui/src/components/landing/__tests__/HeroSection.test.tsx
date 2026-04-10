import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HeroSection } from '../HeroSection';

describe('HeroSection', () => {
  it('renders the main title', () => {
    render(<HeroSection />);
    expect(screen.getByText('AutoSwarm Office')).toBeTruthy();
  });

  it('renders the subtitle text', () => {
    render(<HeroSection />);
    expect(screen.getByText(/Your AI team/)).toBeTruthy();
  });

  it('renders the metrics line', () => {
    render(<HeroSection />);
    expect(screen.getByText('10 AI Agents')).toBeTruthy();
    expect(screen.getByText('4 Departments')).toBeTruthy();
    expect(screen.getByText('HITL Safety')).toBeTruthy();
  });

  it('renders primary CTA linking to the office app', () => {
    render(<HeroSection />);
    const ctaLink = screen.getByText(/Enter the Office/);
    expect(ctaLink).toBeTruthy();
    expect(ctaLink.closest('a')?.getAttribute('href')).toBe(
      'https://agents-app.madfam.io',
    );
  });

  it('renders Try Demo CTA linking to the demo', () => {
    render(<HeroSection />);
    const demoLink = screen.getByText('Try Demo');
    expect(demoLink).toBeTruthy();
    expect(demoLink.closest('a')?.getAttribute('href')).toBe(
      'https://agents-app.madfam.io/demo',
    );
  });
});
