import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HeroSection } from '../HeroSection';

describe('HeroSection', () => {
  it('renders the Selva brand title', () => {
    render(<HeroSection />);
    expect(screen.getByText('Selva')).toBeTruthy();
  });

  it('renders the tagline', () => {
    render(<HeroSection />);
    expect(screen.getByText(/Your AI workforce/)).toBeTruthy();
  });

  it('renders metrics', () => {
    render(<HeroSection />);
    expect(screen.getByText('Named Agents')).toBeTruthy();
    expect(screen.getByText('Built-in Tools')).toBeTruthy();
    expect(screen.getByText('Human-in-the-Loop')).toBeTruthy();
  });

  it('renders primary CTA linking to the demo', () => {
    render(<HeroSection />);
    const ctaLink = screen.getByText(/Try the Live Demo/);
    expect(ctaLink).toBeTruthy();
    expect(ctaLink.closest('a')?.getAttribute('href')).toBe(
      'https://app.selva.town/demo',
    );
  });

  it('renders Sign In CTA linking to the office app', () => {
    render(<HeroSection />);
    const signInLink = screen.getByText('Sign In');
    expect(signInLink).toBeTruthy();
    expect(signInLink.closest('a')?.getAttribute('href')).toBe(
      'https://app.selva.town',
    );
  });
});
