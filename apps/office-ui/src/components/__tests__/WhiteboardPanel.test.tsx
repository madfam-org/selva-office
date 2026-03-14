import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { WhiteboardPanel } from '../WhiteboardPanel';
import type { WhiteboardTool } from '@/hooks/useWhiteboard';

// Mock gameEventBus to avoid Phaser dependency
vi.mock('../../game/PhaserGame', () => ({
  gameEventBus: {
    emit: vi.fn(),
    on: vi.fn(() => vi.fn()),
  },
}));

function renderPanel(
  overrides: Partial<React.ComponentProps<typeof WhiteboardPanel>> = {},
) {
  const defaults = {
    open: true,
    onClose: vi.fn(),
    strokes: [],
    tool: 'pen' as WhiteboardTool,
    color: '#ffffff',
    width: 2,
    colors: ['#ffffff', '#ef4444', '#22c55e', '#3b82f6'] as readonly string[],
    widths: [2, 5, 10] as readonly number[],
    onSendStroke: vi.fn(),
    onClear: vi.fn(),
    onToolChange: vi.fn(),
    onColorChange: vi.fn(),
    onWidthChange: vi.fn(),
    ...overrides,
  };
  return { ...render(<WhiteboardPanel {...defaults} />), props: defaults };
}

describe('WhiteboardPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders when open', () => {
    renderPanel();
    expect(screen.getByText('Whiteboard')).toBeInTheDocument();
    expect(screen.getByTestId('whiteboard-canvas')).toBeInTheDocument();
  });

  it('hides when closed', () => {
    renderPanel({ open: false });
    expect(screen.queryByText('Whiteboard')).not.toBeInTheDocument();
  });

  it('renders canvas element', () => {
    renderPanel();
    const canvas = screen.getByTestId('whiteboard-canvas');
    expect(canvas).toBeInTheDocument();
    expect(canvas.tagName).toBe('CANVAS');
  });

  it('renders tool buttons', () => {
    renderPanel();
    expect(screen.getByLabelText('Pen tool')).toBeInTheDocument();
    expect(screen.getByLabelText('Eraser tool')).toBeInTheDocument();
  });

  it('renders color swatches', () => {
    renderPanel();
    const swatches = screen.getAllByRole('radio');
    // 4 colors + 3 widths = 7 radio elements
    expect(swatches.length).toBeGreaterThanOrEqual(4);
  });

  it('calls onClear when Clear button clicked', () => {
    const { props } = renderPanel();
    fireEvent.click(screen.getByLabelText('Clear whiteboard'));
    expect(props.onClear).toHaveBeenCalledTimes(1);
  });

  it('closes on ESC key', () => {
    const { props } = renderPanel();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on ESC button click', () => {
    const { props } = renderPanel();
    fireEvent.click(screen.getByLabelText('Close whiteboard'));
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onToolChange when tool buttons clicked', () => {
    const { props } = renderPanel();

    fireEvent.click(screen.getByLabelText('Eraser tool'));
    expect(props.onToolChange).toHaveBeenCalledWith('eraser');

    fireEvent.click(screen.getByLabelText('Pen tool'));
    expect(props.onToolChange).toHaveBeenCalledWith('pen');
  });

  it('calls onColorChange when color swatch clicked', () => {
    const { props } = renderPanel();
    fireEvent.click(screen.getByLabelText('Color #ef4444'));
    expect(props.onColorChange).toHaveBeenCalledWith('#ef4444');
  });

  it('calls onWidthChange when width button clicked', () => {
    const { props } = renderPanel();
    fireEvent.click(screen.getByLabelText('Width 5px'));
    expect(props.onWidthChange).toHaveBeenCalledWith(5);
  });

  it('highlights active tool', () => {
    renderPanel({ tool: 'eraser' });
    const eraserBtn = screen.getByLabelText('Eraser tool');
    expect(eraserBtn.getAttribute('aria-pressed')).toBe('true');
    const penBtn = screen.getByLabelText('Pen tool');
    expect(penBtn.getAttribute('aria-pressed')).toBe('false');
  });

  it('highlights active color swatch', () => {
    renderPanel({ color: '#ef4444' });
    const swatch = screen.getByLabelText('Color #ef4444');
    expect(swatch.getAttribute('aria-checked')).toBe('true');
  });

  it('highlights active width', () => {
    renderPanel({ width: 10 });
    const widthBtn = screen.getByLabelText('Width 10px');
    expect(widthBtn.getAttribute('aria-checked')).toBe('true');
  });
});
