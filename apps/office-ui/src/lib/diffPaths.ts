/**
 * Parse the "affected file paths" from a unified diff string.
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
 * Used by `ApprovalPanel` to render an "Affected files" badge on
 * the collapsed card so reviewers can see which file(s) an agent
 * wants to touch before expanding. Pure-function; no DOM deps.
 */

export interface AffectedFile {
  path: string;
  /** `added` (new file), `deleted`, or `modified`. */
  kind: 'added' | 'deleted' | 'modified';
}

const HEADER_ADDED = /^\+\+\+\s+(?:b\/)?(.+?)\s*$/;
const HEADER_DELETED = /^---\s+(?:a\/)?(.+?)\s*$/;
const DEV_NULL = /^\/?dev\/null$/;

export function extractAffectedFiles(diff: string | null | undefined): AffectedFile[] {
  if (!diff) return [];

  const lines = diff.split('\n');
  const files: AffectedFile[] = [];

  // Walk the diff pairwise — a `---` line should be immediately followed
  // by a `+++` line; when both are non-null we have a modification; when
  // one is /dev/null we have an add or delete.
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
      // Orphan `---` without a matching `+++` — skip (malformed or
      // pathological; diff viewers will still render each side).
      i += 1;
      continue;
    }

    const delPath = delMatch[1];
    const addPath = addMatch[1];
    const delIsNull = DEV_NULL.test(delPath);
    const addIsNull = DEV_NULL.test(addPath);

    if (delIsNull && !addIsNull) {
      files.push({ path: addPath, kind: 'added' });
    } else if (addIsNull && !delIsNull) {
      files.push({ path: delPath, kind: 'deleted' });
    } else if (!delIsNull && !addIsNull) {
      // Modification — both sides present; prefer the post-change path.
      files.push({ path: addPath, kind: 'modified' });
    }
    // If both are /dev/null it's a no-op diff header; skip.

    i += 2;
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
