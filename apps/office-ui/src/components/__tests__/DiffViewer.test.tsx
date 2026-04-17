import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DiffViewer } from '../DiffViewer';

describe('DiffViewer', () => {
  it('renders "No diff available" when diff is empty', () => {
    render(<DiffViewer diff="" />);
    expect(screen.getByText(/no diff available/i)).toBeInTheDocument();
  });

  it('renders "No diff available" when diff is null', () => {
    render(<DiffViewer diff={null} />);
    expect(screen.getByText(/no diff available/i)).toBeInTheDocument();
  });

  it('colors addition lines (+) green', () => {
    const diff = '+const x = 1;';
    const { container } = render(<DiffViewer diff={diff} />);
    const line = container.querySelector('.text-emerald-300');
    expect(line).not.toBeNull();
    expect(line?.textContent).toBe('+const x = 1;');
  });

  it('colors deletion lines (-) red', () => {
    const diff = '-const old = 0;';
    const { container } = render(<DiffViewer diff={diff} />);
    const line = container.querySelector('.text-red-300');
    expect(line).not.toBeNull();
    expect(line?.textContent).toBe('-const old = 0;');
  });

  it('colors hunk headers (@@) indigo', () => {
    const diff = '@@ -1,3 +1,4 @@';
    const { container } = render(<DiffViewer diff={diff} />);
    const line = container.querySelector('.text-indigo-300');
    expect(line).not.toBeNull();
  });

  it('does NOT color file-header markers (+++/---) as additions/deletions', () => {
    const diff = '+++ b/src/file.ts\n--- a/src/file.ts';
    const { container } = render(<DiffViewer diff={diff} />);
    // +++ and --- should be slate-italic, never emerald/red
    expect(container.querySelector('.text-emerald-300')).toBeNull();
    expect(container.querySelector('.text-red-300')).toBeNull();
    const italics = container.querySelectorAll('.italic');
    expect(italics.length).toBe(2);
  });

  it('renders all lines of a realistic unified diff', () => {
    const diff = [
      '--- a/src/hello.ts',
      '+++ b/src/hello.ts',
      '@@ -1,3 +1,4 @@',
      ' export function hello() {',
      '-  return "hi";',
      '+  return "hola";',
      '+  // i18n TODO',
      ' }',
    ].join('\n');

    const { container } = render(<DiffViewer diff={diff} />);

    // 2 additions, 1 deletion, 1 hunk header, 2 file headers, 2 context lines
    expect(container.querySelectorAll('.text-emerald-300').length).toBe(2);
    expect(container.querySelectorAll('.text-red-300').length).toBe(1);
    expect(container.querySelectorAll('.text-indigo-300').length).toBe(1);
    expect(container.querySelectorAll('.italic').length).toBe(2);
  });

  it('wraps lines when wrapText=true (mobile)', () => {
    const diff = '+const thisIsAVeryLongLineThatWouldNormallyOverflowHorizontally = "...";';
    const { container } = render(<DiffViewer diff={diff} wrapText />);
    const line = container.querySelector('.whitespace-pre-wrap');
    expect(line).not.toBeNull();
    expect(container.querySelector('.whitespace-pre.overflow-x-auto')).toBeNull();
  });

  it('does not wrap lines by default (desktop)', () => {
    const diff = '+const x = 1;';
    const { container } = render(<DiffViewer diff={diff} />);
    expect(container.querySelector('.whitespace-pre.overflow-x-auto')).not.toBeNull();
    expect(container.querySelector('.whitespace-pre-wrap')).toBeNull();
  });

  it('applies the custom ariaLabel', () => {
    render(<DiffViewer diff="+x" ariaLabel="Proposed diff for Heraldo" />);
    expect(
      screen.getByRole('region', { name: 'Proposed diff for Heraldo' }),
    ).toBeInTheDocument();
  });

  it('renders empty lines as non-breaking space so the line count is preserved', () => {
    const diff = ' line1\n\n line3';
    const { container } = render(<DiffViewer diff={diff} />);
    // 3 lines rendered (line1, blank, line3)
    const rows = container.querySelectorAll('.font-mono');
    expect(rows.length).toBe(3);
  });
});
