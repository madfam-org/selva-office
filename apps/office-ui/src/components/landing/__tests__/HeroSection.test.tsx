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

  it('renders Try Demo CTA link', () => {
    render(<HeroSection />);
    const demoLink = screen.getByText('Try Demo');
    expect(demoLink).toBeTruthy();
    expect(demoLink.closest('a')?.getAttribute('href')).toBe('/demo');
  });

  it('renders Sign In CTA link', () => {
    render(<HeroSection />);
    const signInLink = screen.getByText('Sign In');
    expect(signInLink).toBeTruthy();
    expect(signInLink.closest('a')?.getAttribute('href')).toBe('/login');
  });
});
