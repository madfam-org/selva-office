import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MeetingNotesPanel } from '../MeetingNotesPanel';
import type { MeetingNotes, MeetingNotesStatus } from '../../hooks/useMeetingNotes';

function renderPanel(overrides: Partial<React.ComponentProps<typeof MeetingNotesPanel>> = {}) {
  const defaults = {
    open: true,
    onClose: vi.fn(),
    status: 'idle' as MeetingNotesStatus,
    notes: null as MeetingNotes | null,
    error: null as string | null,
    ...overrides,
  };
  return { ...render(<MeetingNotesPanel {...defaults} />), props: defaults };
}

describe('MeetingNotesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders when open', () => {
    renderPanel();
    expect(screen.getByText('Meeting Notes')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    renderPanel({ open: false });
    expect(screen.queryByText('Meeting Notes')).not.toBeInTheDocument();
  });

  it('shows loading state during processing', () => {
    renderPanel({ status: 'processing' });
    expect(screen.getByText('Generating meeting notes...')).toBeInTheDocument();
  });

  it('shows loading state during dispatching', () => {
    renderPanel({ status: 'dispatching' });
    expect(screen.getByText('Dispatching task...')).toBeInTheDocument();
  });

  it('shows error message', () => {
    renderPanel({ status: 'error', error: 'Something went wrong' });
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('renders summary when completed', () => {
    renderPanel({
      status: 'completed',
      notes: {
        summary: 'We discussed the roadmap.',
        action_items: [],
        transcript: 'Full transcript here.',
      },
    });
    expect(screen.getByText('We discussed the roadmap.')).toBeInTheDocument();
  });

  it('renders action items with checkboxes', () => {
    renderPanel({
      status: 'completed',
      notes: {
        summary: 'Summary',
        action_items: [
          { task: 'Fix login bug', assignee: 'Bob', deadline: 'Friday' },
          { task: 'Write tests', assignee: 'Alice', deadline: 'Monday' },
        ],
        transcript: '',
      },
    });

    expect(screen.getByText('Fix login bug')).toBeInTheDocument();
    expect(screen.getByText('Write tests')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Friday')).toBeInTheDocument();
    expect(screen.getByText('Monday')).toBeInTheDocument();

    // Checkboxes should be present
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(2);
  });

  it('toggles action item checkbox', () => {
    renderPanel({
      status: 'completed',
      notes: {
        summary: 'Summary',
        action_items: [
          { task: 'Fix login bug', assignee: 'Bob', deadline: 'Friday' },
        ],
        transcript: '',
      },
    });

    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).not.toBeChecked();

    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();

    fireEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
  });

  it('expands transcript section', () => {
    renderPanel({
      status: 'completed',
      notes: {
        summary: 'Summary',
        action_items: [],
        transcript: 'The full meeting transcript content.',
      },
    });

    // Transcript should not be visible initially
    expect(screen.queryByText('The full meeting transcript content.')).not.toBeInTheDocument();

    // Click to expand
    const expandBtn = screen.getByText('Full Transcript');
    fireEvent.click(expandBtn);

    expect(screen.getByText('The full meeting transcript content.')).toBeInTheDocument();
  });

  it('calls onClose when ESC button clicked', () => {
    const { props } = renderPanel();
    const escBtn = screen.getByLabelText('Close meeting notes');
    fireEvent.click(escBtn);
    expect(props.onClose).toHaveBeenCalled();
  });

  it('shows idle state message', () => {
    renderPanel({ status: 'idle' });
    expect(screen.getByText('No meeting notes generated yet')).toBeInTheDocument();
  });

  it('shows empty action items message', () => {
    renderPanel({
      status: 'completed',
      notes: {
        summary: 'Summary',
        action_items: [],
        transcript: '',
      },
    });
    expect(screen.getByText('No action items extracted')).toBeInTheDocument();
  });
});
