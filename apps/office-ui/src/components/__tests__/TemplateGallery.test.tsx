import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock dependencies
vi.mock('@/hooks/useFocusTrap', () => ({
  useFocusTrap: () => ({ current: null }),
}));

const mockFetchTemplates = vi.fn();
const mockCreateFromTemplate = vi.fn();

vi.mock('@/hooks/useWorkflowTemplates', () => ({
  useWorkflowTemplates: () => ({
    templates: mockTemplates,
    status: mockStatus,
    error: mockError,
    fetchTemplates: mockFetchTemplates,
    createFromTemplate: mockCreateFromTemplate,
  }),
}));

import { TemplateGallery } from '../workflow-editor/TemplateGallery';
import type { WorkflowTemplate } from '../../hooks/useWorkflowTemplates';

let mockTemplates: WorkflowTemplate[] = [];
let mockStatus: string = 'idle';
let mockError: string | null = null;

const sampleTemplate: WorkflowTemplate = {
  name: '3D Modeling Pipeline',
  description: 'End-to-end 3D modeling workflow with human review',
  filename: '3d-modeling.yaml',
  category: 'Creative',
  node_count: 4,
};

const sampleTemplate2: WorkflowTemplate = {
  name: 'DevOps Pipeline',
  description: 'CI/CD deployment pipeline',
  filename: 'devops-pipeline.yaml',
  category: 'Operations',
  node_count: 6,
};

describe('TemplateGallery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockTemplates = [];
    mockStatus = 'idle';
    mockError = null;
  });

  it('renders nothing when open=false', () => {
    const { container } = render(
      <TemplateGallery open={false} onClose={vi.fn()} onCreated={vi.fn()} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders modal when open=true', () => {
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('displays gallery title', () => {
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);
    expect(screen.getByText('Workflow Templates')).toBeInTheDocument();
  });

  it('shows category filter tabs', () => {
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);
    expect(screen.getByText('All')).toBeInTheDocument();
    expect(screen.getByText('Development')).toBeInTheDocument();
    expect(screen.getByText('Creative')).toBeInTheDocument();
    expect(screen.getByText('Data')).toBeInTheDocument();
    expect(screen.getByText('Operations')).toBeInTheDocument();
  });

  it('calls onClose when [X] button clicked', () => {
    const onClose = vi.fn();
    render(<TemplateGallery open={true} onClose={onClose} onCreated={vi.fn()} />);
    fireEvent.click(screen.getByLabelText('Close template gallery'));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose on ESC key press', () => {
    const onClose = vi.fn();
    render(<TemplateGallery open={true} onClose={onClose} onCreated={vi.fn()} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('shows empty state when no templates', () => {
    mockTemplates = [];
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);
    expect(screen.getByText('No templates found')).toBeInTheDocument();
  });

  it('displays template cards when templates are present', () => {
    mockTemplates = [sampleTemplate];
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);
    expect(screen.getByText('3D Modeling Pipeline')).toBeInTheDocument();
    expect(screen.getByText(/4 nodes/)).toBeInTheDocument();
  });

  it('shows loading state', () => {
    mockStatus = 'loading';
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('shows error message', () => {
    mockError = 'Failed to load templates (500)';
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);
    expect(screen.getByText('Failed to load templates (500)')).toBeInTheDocument();
  });

  it('fetches templates on mount', () => {
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);
    expect(mockFetchTemplates).toHaveBeenCalled();
  });

  it('shows preview when a template card is clicked', () => {
    mockTemplates = [sampleTemplate];
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);

    fireEvent.click(screen.getByLabelText('Select template 3D Modeling Pipeline'));

    expect(screen.getByLabelText('Back to template list')).toBeInTheDocument();
    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(screen.getByLabelText('Custom workflow name')).toBeInTheDocument();
    expect(screen.getByLabelText('Create workflow from template')).toBeInTheDocument();
  });

  it('shows category badge on template card', () => {
    mockTemplates = [sampleTemplate];
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);
    // Category appears both in tab and badge; verify via aria role button on the card
    const card = screen.getByLabelText('Select template 3D Modeling Pipeline');
    expect(card.textContent).toContain('Creative');
  });

  it('filters templates by category', () => {
    mockTemplates = [sampleTemplate, sampleTemplate2];
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);

    // Both visible initially
    expect(screen.getByText('3D Modeling Pipeline')).toBeInTheDocument();
    expect(screen.getByText('DevOps Pipeline')).toBeInTheDocument();

    // Click Creative tab
    fireEvent.click(screen.getByText('Creative'));
    expect(screen.getByText('3D Modeling Pipeline')).toBeInTheDocument();
    expect(screen.queryByText('DevOps Pipeline')).not.toBeInTheDocument();
  });

  it('highlights active category tab', () => {
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);
    const allTab = screen.getByText('All');
    expect(allTab.className).toContain('bg-indigo-600');

    fireEvent.click(screen.getByText('Creative'));
    const creativeTab = screen.getByText('Creative');
    expect(creativeTab.className).toContain('bg-indigo-600');
  });

  it('calls createFromTemplate when Create Workflow is clicked', () => {
    mockTemplates = [sampleTemplate];
    mockCreateFromTemplate.mockResolvedValue({
      id: '1',
      name: '3D Modeling Pipeline',
      yaml_content: 'name: test',
    });

    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);

    // Select template
    fireEvent.click(screen.getByLabelText('Select template 3D Modeling Pipeline'));
    // Click create
    fireEvent.click(screen.getByLabelText('Create workflow from template'));

    expect(mockCreateFromTemplate).toHaveBeenCalledWith('3d-modeling.yaml', undefined);
  });

  it('navigates back from preview to list', () => {
    mockTemplates = [sampleTemplate];
    render(<TemplateGallery open={true} onClose={vi.fn()} onCreated={vi.fn()} />);

    // Select template
    fireEvent.click(screen.getByLabelText('Select template 3D Modeling Pipeline'));
    expect(screen.getByLabelText('Back to template list')).toBeInTheDocument();

    // Go back
    fireEvent.click(screen.getByLabelText('Back to template list'));
    expect(screen.getByLabelText('Select template 3D Modeling Pipeline')).toBeInTheDocument();
  });
});
