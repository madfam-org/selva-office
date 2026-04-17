import { describe, it, expect } from 'vitest';
import { extractAffectedFiles, splitDiffByFile } from '../diffPaths';

describe('extractAffectedFiles', () => {
  it('returns [] for empty / null / undefined diff', () => {
    expect(extractAffectedFiles('')).toEqual([]);
    expect(extractAffectedFiles(null)).toEqual([]);
    expect(extractAffectedFiles(undefined)).toEqual([]);
  });

  it('parses a single-file modification with a/ + b/ prefixes', () => {
    const diff = [
      '--- a/src/hello.ts',
      '+++ b/src/hello.ts',
      '@@ -1,3 +1,4 @@',
      '-old',
      '+new',
    ].join('\n');

    expect(extractAffectedFiles(diff)).toEqual([
      { path: 'src/hello.ts', kind: 'modified' },
    ]);
  });

  it('classifies /dev/null → path as `added`', () => {
    const diff = [
      '--- /dev/null',
      '+++ b/src/brand-new.ts',
      '@@ -0,0 +1,3 @@',
      '+line',
    ].join('\n');

    expect(extractAffectedFiles(diff)).toEqual([
      { path: 'src/brand-new.ts', kind: 'added' },
    ]);
  });

  it('classifies path → /dev/null as `deleted`', () => {
    const diff = [
      '--- a/src/gone.ts',
      '+++ /dev/null',
      '@@ -1,3 +0,0 @@',
      '-line',
    ].join('\n');

    expect(extractAffectedFiles(diff)).toEqual([
      { path: 'src/gone.ts', kind: 'deleted' },
    ]);
  });

  it('parses multi-file diffs', () => {
    const diff = [
      '--- a/src/one.ts',
      '+++ b/src/one.ts',
      '@@ -1 +1 @@',
      '-a',
      '+b',
      '--- a/src/two.ts',
      '+++ b/src/two.ts',
      '@@ -2 +2 @@',
      '-c',
      '+d',
      '--- /dev/null',
      '+++ b/src/three.ts',
      '@@ -0,0 +1 @@',
      '+e',
    ].join('\n');

    expect(extractAffectedFiles(diff)).toEqual([
      { path: 'src/one.ts', kind: 'modified' },
      { path: 'src/two.ts', kind: 'modified' },
      { path: 'src/three.ts', kind: 'added' },
    ]);
  });

  it('handles diffs without a/ b/ prefix (raw paths)', () => {
    const diff = [
      '--- src/hello.ts',
      '+++ src/hello.ts',
      '@@ -1 +1 @@',
      '-a',
      '+b',
    ].join('\n');

    expect(extractAffectedFiles(diff)).toEqual([
      { path: 'src/hello.ts', kind: 'modified' },
    ]);
  });

  it('deduplicates same-file-same-kind entries', () => {
    const diff = [
      '--- a/src/f.ts',
      '+++ b/src/f.ts',
      '@@ -1 +1 @@',
      '-a',
      '+b',
      '--- a/src/f.ts',
      '+++ b/src/f.ts',
      '@@ -5 +5 @@',
      '-c',
      '+d',
    ].join('\n');

    expect(extractAffectedFiles(diff)).toEqual([
      { path: 'src/f.ts', kind: 'modified' },
    ]);
  });

  it('skips orphan --- without a matching +++', () => {
    const diff = [
      '--- a/src/orphan.ts',
      '@@ -1 +1 @@',
      '-a',
      '+b',
    ].join('\n');

    expect(extractAffectedFiles(diff)).toEqual([]);
  });

  it('skips no-op /dev/null → /dev/null headers', () => {
    const diff = [
      '--- /dev/null',
      '+++ /dev/null',
    ].join('\n');

    expect(extractAffectedFiles(diff)).toEqual([]);
  });

  it('preserves non-ASCII and nested paths', () => {
    const diff = [
      '--- a/src/árboles/niño.ts',
      '+++ b/src/árboles/niño.ts',
      '@@ -1 +1 @@',
      '-a',
      '+b',
    ].join('\n');

    expect(extractAffectedFiles(diff)).toEqual([
      { path: 'src/árboles/niño.ts', kind: 'modified' },
    ]);
  });

  it('tolerates whitespace after the path', () => {
    const diff = [
      '--- a/src/hello.ts  ',
      '+++ b/src/hello.ts\t',
      '@@ -1 +1 @@',
    ].join('\n');

    expect(extractAffectedFiles(diff)).toEqual([
      { path: 'src/hello.ts', kind: 'modified' },
    ]);
  });
});

describe('splitDiffByFile', () => {
  it('returns [] for empty / null / undefined diff', () => {
    expect(splitDiffByFile('')).toEqual([]);
    expect(splitDiffByFile(null)).toEqual([]);
    expect(splitDiffByFile(undefined)).toEqual([]);
  });

  it('returns one section for a single-file diff, preserving the body', () => {
    const diff = [
      '--- a/src/hello.ts',
      '+++ b/src/hello.ts',
      '@@ -1 +1 @@',
      '-old',
      '+new',
    ].join('\n');

    const sections = splitDiffByFile(diff);
    expect(sections).toHaveLength(1);
    expect(sections[0].path).toBe('src/hello.ts');
    expect(sections[0].kind).toBe('modified');
    expect(sections[0].body).toBe(diff);
  });

  it('splits a multi-file diff with one section per file', () => {
    const diff = [
      '--- a/src/one.ts',
      '+++ b/src/one.ts',
      '@@ -1 +1 @@',
      '-a',
      '+b',
      '--- a/src/two.ts',
      '+++ b/src/two.ts',
      '@@ -2 +2 @@',
      '-c',
      '+d',
    ].join('\n');

    const sections = splitDiffByFile(diff);
    expect(sections.map((s) => s.path)).toEqual(['src/one.ts', 'src/two.ts']);

    expect(sections[0].body).toBe(
      ['--- a/src/one.ts', '+++ b/src/one.ts', '@@ -1 +1 @@', '-a', '+b'].join(
        '\n',
      ),
    );
    expect(sections[1].body).toBe(
      ['--- a/src/two.ts', '+++ b/src/two.ts', '@@ -2 +2 @@', '-c', '+d'].join(
        '\n',
      ),
    );
  });

  it('each section body is independently renderable (starts with ---)', () => {
    const diff = [
      '--- a/a.ts',
      '+++ b/a.ts',
      '@@ -1 +1 @@',
      '-old',
      '+new',
      '--- a/b.ts',
      '+++ b/b.ts',
      '@@ -1 +1 @@',
      '-old',
      '+new',
    ].join('\n');

    const sections = splitDiffByFile(diff);
    for (const s of sections) {
      expect(s.body.startsWith('---')).toBe(true);
    }
  });

  it('classifies added / deleted / modified the same as extractAffectedFiles', () => {
    const diff = [
      '--- a/src/modified.ts',
      '+++ b/src/modified.ts',
      '@@ -1 +1 @@',
      '-a',
      '+b',
      '--- /dev/null',
      '+++ b/src/created.ts',
      '@@ -0,0 +1 @@',
      '+e',
      '--- a/src/removed.ts',
      '+++ /dev/null',
      '@@ -1 +0,0 @@',
      '-z',
    ].join('\n');

    const sections = splitDiffByFile(diff);
    expect(sections.map((s) => [s.path, s.kind])).toEqual([
      ['src/modified.ts', 'modified'],
      ['src/created.ts', 'added'],
      ['src/removed.ts', 'deleted'],
    ]);
  });

  it('does NOT deduplicate — same file touched twice yields two sections', () => {
    // Deliberate contrast with extractAffectedFiles: the splitter preserves
    // the original diff shape so the UI can render both hunks.
    const diff = [
      '--- a/src/f.ts',
      '+++ b/src/f.ts',
      '@@ -1 +1 @@',
      '-a',
      '+b',
      '--- a/src/f.ts',
      '+++ b/src/f.ts',
      '@@ -5 +5 @@',
      '-c',
      '+d',
    ].join('\n');

    const sections = splitDiffByFile(diff);
    expect(sections).toHaveLength(2);
  });
});
