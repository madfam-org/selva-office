import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock gameEventBus to avoid Phaser dependency
vi.mock('@/game/PhaserGame', () => ({
  gameEventBus: {
    emit: vi.fn(),
    on: vi.fn(() => vi.fn()),
  },
}));

vi.mock('@/hooks/useFocusTrap', () => ({
  useFocusTrap: () => ({ current: null }),
}));

vi.mock('@/hooks/useToast', () => ({
  useToast: () => ({
    addToast: vi.fn(),
  }),
}));

const mockFetchEntries = vi.fn();
const mockFetchEntry = vi.fn();
const mockInstallSkill = vi.fn();
const mockRateSkill = vi.fn();
const mockDeleteSkill = vi.fn();
const mockClearDetail = vi.fn();

vi.mock('@/hooks/useMarketplace', () => ({
  useMarketplace: () => ({
    entries: mockEntries,
    entryDetail: mockEntryDetail,
    status: mockStatus,
    error: mockError,
    fetchEntries: mockFetchEntries,
    fetchEntry: mockFetchEntry,
    publishSkill: vi.fn(),
    rateSkill: mockRateSkill,
    installSkill: mockInstallSkill,
    deleteSkill: mockDeleteSkill,
    clearDetail: mockClearDetail,
  }),
}));

import { SkillMarketplace } from '../SkillMarketplace';
import type { MarketplaceEntry, MarketplaceEntryDetail } from '../../hooks/useMarketplace';

let mockEntries: MarketplaceEntry[] = [];
let mockEntryDetail: MarketplaceEntryDetail | null = null;
let mockStatus: string = 'idle';
let mockError: string | null = null;

const sampleEntry: MarketplaceEntry = {
  id: 'skill-1',
  name: 'Code Review Pro',
  description: 'Automated code review with best practices',
  author: 'alice',
  version: '1.0.0',
  category: 'coding',
  tags: ['review', 'lint'],
  downloads: 42,
  avg_rating: 4.5,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
};

const sampleDetail: MarketplaceEntryDetail = {
  ...sampleEntry,
  yaml_content: 'name: code-review\nsteps:\n  - lint\n  - review',
  readme: 'This skill performs automated code reviews.',
  ratings: [
    { user_id: 'user-abc12345', rating: 5, review: 'Great skill!' },
    { user_id: 'user-def67890', rating: 4, review: null },
  ],
};

describe('SkillMarketplace', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockEntries = [];
    mockEntryDetail = null;
    mockStatus = 'idle';
    mockError = null;
  });

  it('renders nothing when open=false', () => {
    const { container } = render(
      <SkillMarketplace open={false} onClose={vi.fn()} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders modal when open=true', () => {
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('displays marketplace title', () => {
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByText('Skill Marketplace')).toBeInTheDocument();
  });

  it('shows search input', () => {
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByPlaceholderText('Search skills...')).toBeInTheDocument();
  });

  it('shows category filter tabs', () => {
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByText('All')).toBeInTheDocument();
    expect(screen.getByText('Coding')).toBeInTheDocument();
    expect(screen.getByText('Research')).toBeInTheDocument();
    expect(screen.getByText('Communication')).toBeInTheDocument();
    expect(screen.getByText('Data')).toBeInTheDocument();
    expect(screen.getByText('Other')).toBeInTheDocument();
  });

  it('shows sort dropdown', () => {
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByLabelText('Sort by')).toBeInTheDocument();
  });

  it('calls onClose when [X] button clicked', () => {
    const onClose = vi.fn();
    render(<SkillMarketplace open={true} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('Close marketplace'));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose on ESC key press', () => {
    const onClose = vi.fn();
    render(<SkillMarketplace open={true} onClose={onClose} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('shows empty state when no entries', () => {
    mockEntries = [];
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByText('No skills found')).toBeInTheDocument();
  });

  it('displays skill cards when entries are present', () => {
    mockEntries = [sampleEntry];
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByText('Code Review Pro')).toBeInTheDocument();
    expect(screen.getByText(/by alice/)).toBeInTheDocument();
    expect(screen.getByText(/42 installs/)).toBeInTheDocument();
  });

  it('shows loading state', () => {
    mockStatus = 'loading';
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('shows error message', () => {
    mockError = 'Failed to load skills (500)';
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByText('Failed to load skills (500)')).toBeInTheDocument();
  });

  it('fetches entries on mount', () => {
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(mockFetchEntries).toHaveBeenCalled();
  });

  it('shows install button on each card', () => {
    mockEntries = [sampleEntry];
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByLabelText('Install Code Review Pro')).toBeInTheDocument();
  });

  it('calls installSkill when install button clicked', () => {
    mockEntries = [sampleEntry];
    mockInstallSkill.mockResolvedValue(true);
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    fireEvent.click(screen.getByLabelText('Install Code Review Pro'));
    expect(mockInstallSkill).toHaveBeenCalledWith('skill-1');
  });

  it('shows detail view when entry detail is loaded', () => {
    mockEntryDetail = sampleDetail;
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByLabelText('Back to skill list')).toBeInTheDocument();
    expect(screen.getByText('This skill performs automated code reviews.')).toBeInTheDocument();
    expect(screen.getByText(/name: code-review/)).toBeInTheDocument();
  });

  it('shows rating form in detail view', () => {
    mockEntryDetail = sampleDetail;
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByText('Rate this Skill')).toBeInTheDocument();
    expect(screen.getByText('Submit Review')).toBeInTheDocument();
  });

  it('shows existing reviews in detail view', () => {
    mockEntryDetail = sampleDetail;
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByText('Great skill!')).toBeInTheDocument();
    expect(screen.getByText('Reviews')).toBeInTheDocument();
  });

  it('shows delete button in detail view', () => {
    mockEntryDetail = sampleDetail;
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByLabelText('Delete Code Review Pro')).toBeInTheDocument();
  });

  it('calls clearDetail when back button clicked in detail view', () => {
    mockEntryDetail = sampleDetail;
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    fireEvent.click(screen.getByLabelText('Back to skill list'));
    expect(mockClearDetail).toHaveBeenCalled();
  });

  it('suppresses game input when open', async () => {
    const { gameEventBus } = await import('@/game/PhaserGame');
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(gameEventBus.emit).toHaveBeenCalledWith('chat-focus', true);
  });

  it('shows category badge on skill card', () => {
    mockEntries = [sampleEntry];
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByText('coding')).toBeInTheDocument();
  });

  it('shows star rating display', () => {
    mockEntries = [sampleEntry];
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByLabelText('4.5 out of 5 stars')).toBeInTheDocument();
  });

  it('highlights active category tab', () => {
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    const allTab = screen.getByText('All');
    expect(allTab.className).toContain('bg-indigo-600');

    fireEvent.click(screen.getByText('Coding'));
    const codingTab = screen.getByText('Coding');
    expect(codingTab.className).toContain('bg-indigo-600');
  });

  it('shows description section in detail view', () => {
    mockEntryDetail = sampleDetail;
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByText('Description')).toBeInTheDocument();
  });

  it('shows readme section when available', () => {
    mockEntryDetail = sampleDetail;
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByText('Readme')).toBeInTheDocument();
  });

  it('shows YAML preview in detail view', () => {
    mockEntryDetail = sampleDetail;
    render(<SkillMarketplace open={true} onClose={vi.fn()} />);
    expect(screen.getByText('Skill Definition (YAML)')).toBeInTheDocument();
  });
});
