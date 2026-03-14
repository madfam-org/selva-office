import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TilePalette } from '../map-editor/TilePalette';

describe('TilePalette', () => {
  const defaultProps = {
    selectedTile: 1,
    selectedLayer: 'floor',
    onTileSelect: vi.fn(),
    onLayerSelect: vi.fn(),
    onErase: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders layer selector with all layers', () => {
    render(<TilePalette {...defaultProps} />);
    const select = screen.getByTestId('layer-selector');
    expect(select).toBeInTheDocument();
    expect(select).toHaveValue('floor');
  });

  it('calls onLayerSelect when layer changes', () => {
    render(<TilePalette {...defaultProps} />);
    fireEvent.change(screen.getByTestId('layer-selector'), { target: { value: 'walls' } });
    expect(defaultProps.onLayerSelect).toHaveBeenCalledWith('walls');
  });

  it('renders eraser button', () => {
    render(<TilePalette {...defaultProps} />);
    expect(screen.getByTestId('eraser-button')).toBeInTheDocument();
  });

  it('calls onErase when eraser clicked', () => {
    render(<TilePalette {...defaultProps} />);
    fireEvent.click(screen.getByTestId('eraser-button'));
    expect(defaultProps.onErase).toHaveBeenCalled();
  });

  it('calls onTileSelect when a tile is clicked', () => {
    render(<TilePalette {...defaultProps} />);
    const tiles = screen.getAllByRole('button', { name: /Select tile/i });
    expect(tiles.length).toBeGreaterThan(0);
    fireEvent.click(tiles[0]);
    expect(defaultProps.onTileSelect).toHaveBeenCalled();
  });

  it('shows selected tile preview text', () => {
    render(<TilePalette {...defaultProps} />);
    expect(screen.getByText('SELECTED')).toBeInTheDocument();
  });

  it('shows eraser in preview when tile 0 selected', () => {
    render(<TilePalette {...defaultProps} selectedTile={0} />);
    // The selected tile preview should show "Eraser"
    const eraserTexts = screen.getAllByText('Eraser');
    expect(eraserTexts.length).toBeGreaterThanOrEqual(1);
  });
});
