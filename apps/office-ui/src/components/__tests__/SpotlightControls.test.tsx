import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SpotlightControls } from '../SpotlightControls';

describe('SpotlightControls', () => {
  it('renders start button when not active', () => {
    render(
      <SpotlightControls
        active={false}
        presenterName={null}
        isPresenting={false}
        onStart={vi.fn()}
        onStop={vi.fn()}
        visible={true}
      />,
    );
    expect(screen.getByText('SPOTLIGHT')).toBeDefined();
  });

  it('renders stop button when presenting', () => {
    render(
      <SpotlightControls
        active={true}
        presenterName="Alice"
        isPresenting={true}
        onStart={vi.fn()}
        onStop={vi.fn()}
        visible={true}
      />,
    );
    expect(screen.getByText('PRESENTING')).toBeDefined();
    expect(screen.getByRole('button', { name: /stop spotlight/i })).toBeDefined();
  });

  it('shows presenter name when someone else is presenting', () => {
    render(
      <SpotlightControls
        active={true}
        presenterName="Bob"
        isPresenting={false}
        onStart={vi.fn()}
        onStop={vi.fn()}
        visible={true}
      />,
    );
    expect(screen.getByText('Bob is presenting')).toBeDefined();
  });

  it('does not render when not visible', () => {
    const { container } = render(
      <SpotlightControls
        active={false}
        presenterName={null}
        isPresenting={false}
        onStart={vi.fn()}
        onStop={vi.fn()}
        visible={false}
      />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('calls onStart when start button clicked', () => {
    const onStart = vi.fn();
    render(
      <SpotlightControls
        active={false}
        presenterName={null}
        isPresenting={false}
        onStart={onStart}
        onStop={vi.fn()}
        visible={true}
      />,
    );
    fireEvent.click(screen.getByText('SPOTLIGHT'));
    expect(onStart).toHaveBeenCalledOnce();
  });

  it('calls onStop when stop button clicked', () => {
    const onStop = vi.fn();
    render(
      <SpotlightControls
        active={true}
        presenterName="Alice"
        isPresenting={true}
        onStart={vi.fn()}
        onStop={onStop}
        visible={true}
      />,
    );
    fireEvent.click(screen.getByText('PRESENTING'));
    expect(onStop).toHaveBeenCalledOnce();
  });
});
