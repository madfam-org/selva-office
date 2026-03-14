import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MusicStatus } from '../MusicStatus';

describe('MusicStatus', () => {
  it('renders current status text', () => {
    render(<MusicStatus currentStatus="🎵 Working" onStatusChange={vi.fn()} />);
    const button = screen.getByRole('button', { name: /music status.*working/i });
    expect(button).toBeDefined();
    expect(button.textContent).toContain('Working');
  });

  it('shows placeholder when no status set', () => {
    render(<MusicStatus currentStatus="" onStatusChange={vi.fn()} />);
    expect(screen.getByText('\u{1F3B5} Set status...')).toBeDefined();
  });

  it('shows preset buttons when editing', () => {
    render(<MusicStatus currentStatus="" onStatusChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /set music status/i }));
    expect(screen.getByText('\u{1F3B5} Working')).toBeDefined();
    expect(screen.getByText('\u{1F3A7} In the zone')).toBeDefined();
    expect(screen.getByText('\u2615 Coffee break')).toBeDefined();
  });

  it('calls onStatusChange when preset selected', () => {
    const onChange = vi.fn();
    render(<MusicStatus currentStatus="" onStatusChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /set music status/i }));
    fireEvent.click(screen.getByText('\u{1F4BB} Coding'));
    expect(onChange).toHaveBeenCalledWith('\u{1F4BB} Coding');
  });

  it('respects max length in input', () => {
    const onChange = vi.fn();
    render(<MusicStatus currentStatus="" onStatusChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /set music status/i }));

    const input = screen.getByLabelText('Music status input');
    expect(input).toBeDefined();
    expect(input.getAttribute('maxLength')).toBe('50');
  });

  it('has accessible label', () => {
    render(<MusicStatus currentStatus="Testing" onStatusChange={vi.fn()} />);
    const button = screen.getByRole('button', { name: /music status.*testing/i });
    expect(button).toBeDefined();
  });
});
