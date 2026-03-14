import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the heavy dependencies
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: { children: React.ReactNode }) => <div data-testid="react-flow">{children}</div>,
  ReactFlowProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Background: () => <div data-testid="rf-background" />,
  BackgroundVariant: { Dots: 'dots', Lines: 'lines', Cross: 'cross' },
  Controls: () => <div data-testid="rf-controls" />,
  MiniMap: () => <div data-testid="rf-minimap" />,
  useNodesState: () => [[], vi.fn(), vi.fn()],
  useEdgesState: () => [[], vi.fn(), vi.fn()],
  addEdge: vi.fn(),
  Position: { Top: 'top', Bottom: 'bottom' },
  Handle: () => <div />,
  BaseEdge: () => <div />,
  getBezierPath: () => ['', 0, 0],
  EdgeLabelRenderer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/game/PhaserGame', () => ({
  gameEventBus: {
    emit: vi.fn(),
    on: vi.fn(() => vi.fn()),
  },
}));

vi.mock('@/hooks/useFocusTrap', () => ({
  useFocusTrap: () => ({ current: null }),
}));

vi.mock('@/hooks/useWorkflow', () => ({
  useWorkflow: () => ({
    status: 'idle' as const,
    error: null,
    workflowList: [],
    workflow: null,
    validationResult: null,
    loadList: vi.fn(),
    load: vi.fn(),
    save: vi.fn(),
    validate: vi.fn(),
    deleteWorkflow: vi.fn(),
    importYaml: vi.fn(),
    exportYaml: vi.fn(),
  }),
}));

vi.mock('@/hooks/useExecutionLog', () => ({
  useExecutionLog: () => ({
    events: [],
    clearEvents: vi.fn(),
  }),
}));

vi.mock('@/hooks/useTaskDispatch', () => ({
  useTaskDispatch: () => ({
    dispatch: vi.fn(),
    status: 'idle',
    error: null,
    lastDispatchedTask: null,
    reset: vi.fn(),
  }),
}));

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { WorkflowEditor } from '../workflow-editor/WorkflowEditor';

describe('WorkflowEditor', () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    officeState: null,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not render when closed', () => {
    const { container } = render(<WorkflowEditor {...defaultProps} open={false} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders when open', () => {
    render(<WorkflowEditor {...defaultProps} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('renders node palette with NODES header', () => {
    render(<WorkflowEditor {...defaultProps} />);
    expect(screen.getByText('NODES')).toBeInTheDocument();
  });

  it('renders editor toolbar with workflow name input', () => {
    render(<WorkflowEditor {...defaultProps} />);
    const input = screen.getByDisplayValue('Untitled Workflow');
    expect(input).toBeInTheDocument();
  });

  it('renders execution log', () => {
    render(<WorkflowEditor {...defaultProps} />);
    expect(screen.getByText(/EXECUTION LOG/)).toBeInTheDocument();
  });

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn();
    render(<WorkflowEditor {...defaultProps} onClose={onClose} />);
    fireEvent.click(screen.getByText('✕ Close'));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose on ESC key', () => {
    const onClose = vi.fn();
    render(<WorkflowEditor {...defaultProps} onClose={onClose} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('emits chat-focus true when opened', async () => {
    const { gameEventBus } = await import('@/game/PhaserGame');
    render(<WorkflowEditor {...defaultProps} />);
    expect(gameEventBus.emit).toHaveBeenCalledWith('chat-focus', true);
  });
});
