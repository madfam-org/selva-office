import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MapCanvas } from '../map-editor/MapCanvas';

// Mock ResizeObserver
class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver;

// Mock canvas context
const mockCtx = {
  clearRect: vi.fn(),
  fillRect: vi.fn(),
  strokeRect: vi.fn(),
  fillText: vi.fn(),
  beginPath: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  stroke: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  scale: vi.fn(),
  translate: vi.fn(),
  set imageSmoothingEnabled(_v: boolean) {},
  set fillStyle(_v: string) {},
  set strokeStyle(_v: string) {},
  set lineWidth(_v: number) {},
  set font(_v: string) {},
};

HTMLCanvasElement.prototype.getContext = vi.fn(() => mockCtx) as unknown as typeof HTMLCanvasElement.prototype.getContext;

describe('MapCanvas', () => {
  const defaultMap = {
    width: 5,
    height: 5,
    tileWidth: 32,
    tileHeight: 32,
    layers: [
      { name: 'floor', data: new Array(25).fill(1), visible: true },
      { name: 'walls', data: new Array(25).fill(0), visible: true },
    ],
    objects: [],
  };

  const defaultProps = {
    map: defaultMap,
    selectedTile: 1,
    selectedLayer: 'floor',
    tool: 'paint' as const,
    showGrid: true,
    selectedObject: null,
    onTilePlace: vi.fn(),
    onTileErase: vi.fn(),
    onObjectSelect: vi.fn(),
    onPushUndo: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders canvas element', () => {
    render(<MapCanvas {...defaultProps} />);
    expect(screen.getByTestId('map-canvas')).toBeInTheDocument();
  });

  it('renders container div', () => {
    render(<MapCanvas {...defaultProps} />);
    expect(screen.getByTestId('map-canvas-container')).toBeInTheDocument();
  });

  it('renders zoom indicator', () => {
    render(<MapCanvas {...defaultProps} />);
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('draws grid when showGrid is true', () => {
    render(<MapCanvas {...defaultProps} showGrid={true} />);
    // The canvas context should have been called for grid drawing
    // (happens in the draw effect)
    expect(mockCtx.save).toHaveBeenCalled();
  });
});
