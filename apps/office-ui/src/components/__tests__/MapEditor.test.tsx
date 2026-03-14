import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock ResizeObserver before any component imports
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

vi.mock('@/game/PhaserGame', () => ({
  gameEventBus: {
    emit: vi.fn(),
    on: vi.fn(() => vi.fn()),
  },
}));

vi.mock('@/hooks/useFocusTrap', () => ({
  useFocusTrap: () => ({ current: null }),
}));

vi.mock('@/hooks/useMapEditor', () => ({
  useMapEditor: () => ({
    map: {
      width: 10,
      height: 10,
      tileWidth: 32,
      tileHeight: 32,
      layers: [
        { name: 'floor', data: new Array(100).fill(0), visible: true },
        { name: 'walls', data: new Array(100).fill(0), visible: true },
        { name: 'furniture', data: new Array(100).fill(0), visible: true },
        { name: 'decorations', data: new Array(100).fill(0), visible: true },
        { name: 'collision', data: new Array(100).fill(0), visible: true },
      ],
      objects: [],
    },
    selectedTile: 1,
    selectedLayer: 'floor',
    selectedObject: null,
    tool: 'paint' as const,
    status: 'idle' as const,
    error: null,
    mapList: [],
    currentMapId: null,
    mapName: 'Test Map',
    canUndo: false,
    canRedo: false,
    setSelectedTile: vi.fn(),
    setSelectedLayer: vi.fn(),
    setTool: vi.fn(),
    setMapName: vi.fn(),
    placeTile: vi.fn(),
    eraseTile: vi.fn(),
    pushUndo: vi.fn(),
    placeObject: vi.fn(),
    removeObject: vi.fn(),
    selectObject: vi.fn(),
    updateObject: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    loadList: vi.fn(),
    load: vi.fn(),
    save: vi.fn(),
    exportTmj: vi.fn(() => '{}'),
    importTmj: vi.fn(),
    newMap: vi.fn(),
  }),
}));

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { MapEditor } from '../map-editor/MapEditor';

describe('MapEditor', () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not render when closed', () => {
    const { container } = render(<MapEditor {...defaultProps} open={false} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders when open', () => {
    render(<MapEditor {...defaultProps} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('renders toolbar with map name input', () => {
    render(<MapEditor {...defaultProps} />);
    const input = screen.getByDisplayValue('Test Map');
    expect(input).toBeInTheDocument();
  });

  it('renders tile palette with layer selector', () => {
    render(<MapEditor {...defaultProps} />);
    expect(screen.getByTestId('layer-selector')).toBeInTheDocument();
  });

  it('renders canvas container', () => {
    render(<MapEditor {...defaultProps} />);
    expect(screen.getByTestId('map-canvas-container')).toBeInTheDocument();
  });

  it('renders grid toggle button', () => {
    render(<MapEditor {...defaultProps} />);
    expect(screen.getByTestId('grid-toggle')).toBeInTheDocument();
  });

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn();
    render(<MapEditor {...defaultProps} onClose={onClose} />);
    fireEvent.click(screen.getByText('Close'));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose on ESC key', () => {
    const onClose = vi.fn();
    render(<MapEditor {...defaultProps} onClose={onClose} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('emits chat-focus true when opened', async () => {
    const { gameEventBus } = await import('@/game/PhaserGame');
    render(<MapEditor {...defaultProps} />);
    expect(gameEventBus.emit).toHaveBeenCalledWith('chat-focus', true);
  });

  it('renders objects panel', () => {
    render(<MapEditor {...defaultProps} />);
    expect(screen.getByText('Objects')).toBeInTheDocument();
  });

  it('renders properties panel', () => {
    render(<MapEditor {...defaultProps} />);
    expect(screen.getByText('Properties')).toBeInTheDocument();
  });
});
