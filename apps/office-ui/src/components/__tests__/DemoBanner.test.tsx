import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DemoBanner } from '../DemoBanner';

// Mock useDemoMode hook
const mockConvertToReal = vi.fn();
const mockExitDemo = vi.fn();

vi.mock('@/hooks/useDemoMode', () => ({
  useDemoMode: () => ({
    isDemo: true,
    convertToReal: mockConvertToReal,
    exitDemo: mockExitDemo,
  }),
}));

describe('DemoBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders demo mode text', () => {
    render(<DemoBanner />);
    expect(screen.getByText('DEMO MODE')).toBeTruthy();
    expect(screen.getByText('Actions are simulated')).toBeTruthy();
  });

  it('renders sign in button', () => {
    render(<DemoBanner />);
    expect(screen.getByText('Sign In for Real')).toBeTruthy();
  });

  it('renders exit button', () => {
    render(<DemoBanner />);
    expect(screen.getByText('Exit')).toBeTruthy();
  });

  it('calls convertToReal when "Sign In for Real" is clicked', () => {
    render(<DemoBanner />);
    fireEvent.click(screen.getByText('Sign In for Real'));
    expect(mockConvertToReal).toHaveBeenCalledTimes(1);
  });

  it('calls exitDemo when "Exit" is clicked', () => {
    render(<DemoBanner />);
    fireEvent.click(screen.getByText('Exit'));
    expect(mockExitDemo).toHaveBeenCalledTimes(1);
  });
});
