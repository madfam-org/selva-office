import { render, screen, fireEvent } from '@testing-library/react';
import { createRef } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { PixelButton } from '../pixelact/pixel-button';
import { PixelInput } from '../pixelact/pixel-input';

describe('PixelButton', () => {
  it('renders with default variant', () => {
    render(<PixelButton>Click</PixelButton>);
    const button = screen.getByRole('button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveClass('pxa-btn');
    expect(button).toHaveClass('bg-pixelact-primary');
  });

  it('renders children text', () => {
    render(<PixelButton>Hello</PixelButton>);
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('applies custom className', () => {
    render(<PixelButton className="my-class">Styled</PixelButton>);
    expect(screen.getByRole('button')).toHaveClass('my-class');
  });

  it('fires onClick handler', () => {
    const handleClick = vi.fn();
    render(<PixelButton onClick={handleClick}>Click</PixelButton>);
    fireEvent.click(screen.getByRole('button'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('is disabled when disabled prop is true', () => {
    render(<PixelButton disabled>Disabled</PixelButton>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('forwards ref', () => {
    const ref = createRef<HTMLButtonElement>();
    render(<PixelButton ref={ref}>Ref</PixelButton>);
    expect(ref.current).toBeInstanceOf(HTMLButtonElement);
  });

  it('renders with secondary variant', () => {
    render(<PixelButton variant="secondary">Secondary</PixelButton>);
    expect(screen.getByRole('button')).toHaveClass('bg-pixelact-muted');
  });

  it('renders with destructive variant', () => {
    render(<PixelButton variant="destructive">Delete</PixelButton>);
    expect(screen.getByRole('button')).toHaveClass('bg-semantic-error');
  });

  it('renders with success variant', () => {
    render(<PixelButton variant="success">OK</PixelButton>);
    expect(screen.getByRole('button')).toHaveClass('bg-semantic-success');
  });

  it('renders with ghost variant', () => {
    render(<PixelButton variant="ghost">Ghost</PixelButton>);
    expect(screen.getByRole('button')).toHaveClass('bg-transparent');
  });

  it('renders with sm size', () => {
    render(<PixelButton size="sm">Small</PixelButton>);
    expect(screen.getByRole('button')).toHaveClass('text-retro-xs');
  });

  it('renders with lg size', () => {
    render(<PixelButton size="lg">Large</PixelButton>);
    expect(screen.getByRole('button')).toHaveClass('text-retro-base');
  });
});

describe('PixelInput', () => {
  it('renders an input element', () => {
    render(<PixelInput placeholder="Type here" />);
    const input = screen.getByPlaceholderText('Type here');
    expect(input).toBeInTheDocument();
    expect(input.tagName).toBe('INPUT');
    expect(input).toHaveClass('pxa-input');
  });

  it('applies custom className', () => {
    render(<PixelInput className="my-input" placeholder="test" />);
    expect(screen.getByPlaceholderText('test')).toHaveClass('my-input');
  });

  it('forwards ref', () => {
    const ref = createRef<HTMLInputElement>();
    render(<PixelInput ref={ref} placeholder="ref" />);
    expect(ref.current).toBeInstanceOf(HTMLInputElement);
  });

  it('accepts type prop', () => {
    render(<PixelInput type="password" placeholder="pw" />);
    expect(screen.getByPlaceholderText('pw')).toHaveAttribute('type', 'password');
  });

  it('handles value changes', () => {
    const handleChange = vi.fn();
    render(<PixelInput onChange={handleChange} placeholder="change" />);
    fireEvent.change(screen.getByPlaceholderText('change'), { target: { value: 'hello' } });
    expect(handleChange).toHaveBeenCalledTimes(1);
  });
});
