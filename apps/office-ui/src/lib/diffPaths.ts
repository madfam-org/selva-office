/**
 * Parse the "affected file paths" from a unified diff string, and
 * optionally split a multi-file diff into per-file sections so the UI
 * can navigate between files without a backend worktree browser.
 *
 * A unified diff carries each file in a header block of the form:
 *
 *     --- a/src/hello.ts
 *     +++ b/src/hello.ts
 *     @@ -1,3 +1,4 @@
 *     ...
 *
 * We prefer the `+++ b/<path>` line (the post-change file) because
 * it carries the path the reviewer is actually being asked to
 * accept. For new files, the `--- a/...` line shows `/dev/null`,
 * which we filter out. For deletions, the `+++ b/...` line shows
 * `/dev/null`, so we fall back to the `--- a/<path>` line in that
 * case.
 *
 * Pure-function; no DOM deps.
 */

export interface AffectedFile {
  path: string;
  /** `added` (new file), `deleted`, or `modified`. */
  kind: 'added' | 'deleted' | 'modified';
}

export interface DiffSection extends AffectedFile {
  /** The per-file diff body including its `---` / `+++` / `@@` headers. */
  body: string;
}

const HEADER_ADDED = /^\+\+\+\s+(?:b\/)?(.+?)\s*$/;
const HEADER_DELETED = /^---\s+(?:a\/)?(.+?)\s*$/;
const DEV_NULL = /^\/?dev\/null$/;

interface InternalSection {
  startIdx: number;
  nextIdx: number;
  delPath: string;
  addPath: string;
}

/**
 * Walk a unified diff and yield one record per `--- … / +++ …` pair.
 * Shared by `extractAffectedFiles` and `splitDiffByFile` so there's
 * exactly one place that knows how the header pairs line up.
 */
function findSections(diff: string): { lines: string[]; sections: InternalSection[] } {
  const lines = diff.split('\n');
  const sections: InternalSection[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const delMatch = HEADER_DELETED.exec(line);
    if (!delMatch) {
      i += 1;
      continue;
    }
    const nextLine = lines[i + 1] ?? '';
    const addMatch = HEADER_ADDED.exec(nextLine);
    if (!addMatch) {
      // Orphan `---` without a matching `+++` — skip (malformed).
      i += 1;
      continue;
    }
    sections.push({
      startIdx: i,
      nextIdx: i + 2,
      delPath: delMatch[1],
      addPath: addMatch[1],
    });
    i += 2;
  }
  return { lines, sections };
}

function classify(
  delPath: string,
  addPath: string,
): { path: string; kind: AffectedFile['kind'] } | null {
  const delIsNull = DEV_NULL.test(delPath);
  const addIsNull = DEV_NULL.test(addPath);
  if (delIsNull && !addIsNull) return { path: addPath, kind: 'added' };
  if (addIsNull && !delIsNull) return { path: delPath, kind: 'deleted' };
  if (!delIsNull && !addIsNull) return { path: addPath, kind: 'modified' };
  return null;
}

export function extractAffectedFiles(diff: string | null | undefined): AffectedFile[] {
  if (!diff) return [];
  const { sections } = findSections(diff);
  const files: AffectedFile[] = [];
  for (const s of sections) {
    const c = classify(s.delPath, s.addPath);
    if (c) files.push(c);
  }
  // Deduplicate — a single file touched twice in one diff still counts once.
  const seen = new Set<string>();
  return files.filter((f) => {
    const key = `${f.kind}:${f.path}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/**
 * Split a multi-file unified diff into one `DiffSection` per file.
 *
 * Each section carries the full original text from its `--- ` header
 * up to the next file's `--- ` header (or end-of-diff), so the section
 * body is independently renderable by `DiffViewer`. This lets the
 * approval UI show a per-file picker / navigation without needing a
 * backend worktree endpoint — the diff already carries the full
 * proposed change.
 *
 * Returns an empty array for empty / null / unparseable input.
 */
export function splitDiffByFile(diff: string | null | undefined): DiffSection[] {
  if (!diff) return [];
  const { lines, sections: raw } = findSections(diff);
  if (raw.length === 0) return [];

  const out: DiffSection[] = [];
  for (let i = 0; i < raw.length; i += 1) {
    const section = raw[i];
    const endIdx = i + 1 < raw.length ? raw[i + 1].startIdx : lines.length;
    const body = lines.slice(section.startIdx, endIdx).join('\n');
    const c = classify(section.delPath, section.addPath);
    if (c) out.push({ ...c, body });
  }
  return out;
}
