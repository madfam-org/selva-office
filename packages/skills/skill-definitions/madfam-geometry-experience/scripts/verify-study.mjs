#!/usr/bin/env node
// Original MADFAM local-draft helper. Reads trusted study data; never imports its code.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';

function requireValue(ok, message) { if (!ok) throw new Error(message); }
export function canonical(value) {
  if (value === null || ['boolean', 'string'].includes(typeof value)) return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(Object.is(value, -0) ? 0 : value);
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype)
    return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  throw new Error('Expected finite plain JSON');
}
const sha = value => createHash('sha256').update(value).digest('hex');
export const digest = value => sha(canonical(value));
const same = (a, b, message) => requireValue(canonical(a) === canonical(b), message);
const finitePositive = value => typeof value === 'number' && Number.isFinite(value) && value > 0;
const safeFile = value => typeof value === 'string' && /^[\w.-]+$/.test(value) && !['.', '..'].includes(value);

export function verifySourceProbe(probe) {
  requireValue(probe.status === 'source-lock-only' && probe.geometry_rendered === false,
    'Source probe must retain its unexecuted, source-lock-only status');
  requireValue(Array.isArray(probe.references) && probe.references.length > 0, 'No source references read');
  for (const ref of probe.references) {
    const { instance_digest, ...source } = ref.source;
    requireValue(/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/.test(source.repository), 'Explicit repository required');
    requireValue(/^[a-f0-9]{40}$/.test(source.commit), 'Full immutable source commit required');
    requireValue(/^[a-f0-9]{64}$/.test(source.content_sha256), 'Source content digest required');
    requireValue(typeof source.path === 'string' && source.path.length > 0 && !source.path.startsWith('/') &&
      !source.path.includes('\\') && !source.path.split('/').some(p => ['', '.', '..'].includes(p)), 'Unsafe source path');
    requireValue(typeof source.engine === 'string' && source.engine.length > 0, 'Engine identity required');
    requireValue(source.parameters && typeof source.parameters === 'object' && !Array.isArray(source.parameters), 'Resolved parameters required');
    requireValue(digest(source) === instance_digest, 'Source lock digest mismatch');
    requireValue(typeof ref.scope === 'string' && ref.scope.length > 0, 'Source probe scope required');
  }
  requireValue(Array.isArray(probe.current_assembly_allowed_cartridge_commons), 'Missing assembly capability declaration');
  requireValue(probe.mixed_assembly_status === 'unsupported-by-current-ASM-1-schema', 'This probe adapter has no mixed assembly support');
  return { references_read: probe.references.length, stored_lock_integrity: true,
    source_bytes_rechecked: false, runtime_closure_verified: false, geometry_rendered: false };
}

export function verifyDataset(dataset, report, exportsByFit) {
  canonical(dataset); canonical(report);
  requireValue(dataset.format === 'madfam.strand-study-preview' && dataset.version === '0.1.0', 'Unsupported preview format/version');
  requireValue(dataset.variants?.length > 0, 'No variants read');
  requireValue(digest(dataset.source) === dataset.source_digest && report.source === dataset.source_digest, 'Source digest mismatch');
  requireValue(report.variants?.length === dataset.variants.length, 'Variant coverage mismatch');
  const fits = new Set(); let views = 0, strands = 0, crossings = 0;
  for (const variant of dataset.variants) {
    const s = variant.snapshot, id = variant.instance_digest;
    requireValue(finitePositive(variant.circumference) && !fits.has(variant.circumference), 'Invalid or repeated fit');
    fits.add(variant.circumference);
    requireValue(s.format === 'madfam.strand-study' && s.version === '0.1.0' && s.units === 'mm', 'Unsupported snapshot format, version or units');
    requireValue(s.parameters.layout === 'cuff' && s.parameters.inner_circumference_mm === variant.circumference, 'Fit/snapshot mismatch');
    requireValue(digest({ source_digest: dataset.source_digest, snapshot: s }) === id, 'Snapshot digest mismatch');
    same(exportsByFit.get(variant.circumference), { source: dataset.source_digest, instance_digest: id, snapshot: s }, 'Export/preview mismatch');
    const r = report.variants.find(v => v.instance_digest === id);
    requireValue(r && r.circumference_mm === variant.circumference, 'Report/preview mismatch');
    same(r.verification, s.verification, 'Verification report differs from snapshot');
    requireValue(s.paths?.length === 3 && new Set(s.paths.map(p => p.id)).size === 3, 'Study requires three distinct strands');
    same(s.paths.map(p => p.id), ['A', 'B', 'C'], 'Unsupported strand identity ordering');
    requireValue(finitePositive(s.parameters.finishing_allowance_mm), 'Missing finishing allowance');
    for (const p of s.paths) {
      requireValue(p.points?.length >= 2 && p.points.every(q => Array.isArray(q) && q.length === 3 && q.every(Number.isFinite)), 'Invalid 3D path');
      requireValue(finitePositive(p.centreline_length_mm) && finitePositive(p.cut_length_estimate_mm), 'Invalid length');
      requireValue(Math.abs(p.cut_length_estimate_mm - p.centreline_length_mm - s.parameters.finishing_allowance_mm) < 1e-9, 'Cut length/allowance mismatch');
      same(p.terminals?.start, p.points[0], 'Start terminal/path mismatch');
      same(p.terminals?.end, p.points.at(-1), 'End terminal/path mismatch');
      requireValue(p.terminals.start_lane === ['A', 'B', 'C'].indexOf(p.id) &&
        p.terminals.end_lane === s.end_permutation.indexOf(p.id), 'Terminal lane identity mismatch');
    }
    same(r.paths, s.paths.map(p => ({ id: p.id, centreline_mm: p.centreline_length_mm, cut_estimate_mm: p.cut_length_estimate_mm })), 'Report quantity mismatch');
    requireValue(s.crossings?.length > 0 && s.crossings.length === s.parameters.word.length && variant.frames.length === s.crossings.length, 'Crossing coverage mismatch');
    let slots = ['A', 'B', 'C'];
    for (let i = 0; i < s.crossings.length; i++) {
      const event = s.crossings[i], generator = s.parameters.word[i], lane = Math.abs(generator) - 1;
      requireValue([1, -1, 2, -2].includes(generator) && event.index === i && event.generator === generator, 'Invalid signed crossing');
      same(event.before, slots, 'Crossing permutation discontinuity');
      requireValue(event.over === slots[lane + (generator > 0 ? 0 : 1)] && event.under === slots[lane + (generator > 0 ? 1 : 0)], 'Contradictory over/under order');
      [slots[lane], slots[lane + 1]] = [slots[lane + 1], slots[lane]];
      same(event.after, slots, 'Crossing result mismatch');
      const state = variant.frames[i].state;
      same(state.event, event, 'Frame refers to another crossing');
      same(state.slots, slots, 'Frame permutation mismatch');
      same(state.active, [event.over, event.under], 'Highlight mismatch');
      requireValue(state.completed === i + 1 && state.total === s.crossings.length, 'Step readout mismatch');
      requireValue(state.readout === `Step ${i + 1} of ${s.crossings.length}: ${event.over} passes over ${event.under}`, 'Text readout mismatch');
    }
    same(s.end_permutation, slots, 'End permutation mismatch');
    same(r.cuff_audit, variant.cuff.audit, 'Cuff audit report mismatch');
    same(r.crossing_audits, variant.frames.map(f => f.audit), 'Crossing audit report mismatch');
    for (const view of [variant.cuff, ...variant.frames]) {
      requireValue(typeof view.svg === 'string' && view.svg.includes('<svg'), 'Missing SVG view');
      const a = view.audit;
      requireValue(a.physical_strands === 3 && Number.isInteger(a.render_chunks) && a.render_chunks >= 3, 'Physical parts/render chunks mismatch');
      requireValue(Number.isInteger(a.overlapping_pairs_read) && a.overlapping_pairs_read > 0, 'Zero sampled pairs provide no painter evidence');
      requireValue(a.wrong_order === 0 && a.missing_shapes === 0 && a.scope?.length > 0, 'Failed or unscoped illustration audit');
      views++;
    }
    requireValue(s.verification.strands_read === 3 && s.verification.crossings_read === s.crossings.length && s.verification.crossing_order === true, 'Stored check counts mismatch');
    requireValue(s.verification.unverified?.length > 0 && s.verification.terminal_state?.length > 0, 'Missing physical/termination limitations');
    const c = s.verification.clearance;
    requireValue(Number.isInteger(c.exact_segment_pairs_tested) && c.exact_segment_pairs_tested > 0 && c.scope?.length > 0, 'Missing clearance coverage/scope');
    requireValue(Number.isFinite(c.surface_lower_bound_mm) && c.surface_lower_bound_mm >= s.parameters.clearance_mm, 'Stored clearance is below request');
    strands += 3; crossings += s.crossings.length;
  }
  return { variants_read: fits.size, strand_instances_read: strands, crossings_read: crossings, stored_views_read: views };
}

export function verifyDirectory(directory, sourceProbe) {
  const root = resolve(directory), read = name => readFileSync(join(root, name), 'utf8');
  const html = read('index.html'), match = html.match(/<script id="study-data" type="application\/json">([\s\S]*?)<\/script>/);
  requireValue(match, 'Missing study-data JSON');
  const d = JSON.parse(match[1]), report = JSON.parse(read('artifacts/verification.json'));
  same(Object.keys(d.source).sort(), ['model.mjs', 'geometry.mjs', 'presentation.mjs', 'lock.mjs'].sort(), 'Unknown source coverage');
  for (const [name, expected] of Object.entries(d.source)) {
    requireValue(safeFile(name) && sha(read(name)) === expected, `Source changed since build: ${name}`);
  }
  requireValue(d.anatomy?.repository === 'https://github.com/wheresryan22/anatomy' && /^[a-f0-9]{40}$/.test(d.anatomy.commit) && d.anatomy.license === 'MIT', 'Missing pinned Anatomy identity/notice');
  same(d.anatomy, JSON.parse(read('vendor/anatomy/SOURCE.json')), 'Vendor lock differs from page');
  requireValue(Object.keys(d.anatomy.files).length > 0 && d.anatomy.files.LICENSE, 'No vendor files/licence read');
  for (const [name, expected] of Object.entries(d.anatomy.files)) {
    requireValue(safeFile(name) && sha(read('vendor/anatomy/' + name)) === expected, `Vendor file changed: ${name}`);
  }
  const exported = new Map(d.variants.map(v => {
    requireValue(finitePositive(v.circumference), 'Invalid export fit');
    return [v.circumference, JSON.parse(read(`artifacts/cuff-${v.circumference}.json`))];
  }));
  const counts = verifyDataset(d, report, exported);
  requireValue(report.page_bytes === Buffer.byteLength(html), 'Stored page size mismatch');
  return { status: 'passed', scope: 'stored-data integrity and parity for strand study 0.1.0', ...counts,
    source_files_read: Object.keys(d.source).length, vendor_files_read: Object.keys(d.anatomy.files).length,
    geometry_recomputed: false, illustration_reaudited: false, browser_exercised: false,
    manufacturing_qualified: false, runtime_closure_verified: false,
    source_probe: sourceProbe ? verifySourceProbe(JSON.parse(readFileSync(sourceProbe, 'utf8'))) : null,
    limitations: ['Unkeyed hashes detect inconsistency, not trusted authorship or coordinated fabrication of evidence.',
      'UI source is outside the model digest; browser tests must establish rendered behavior.',
      'Stored numerical and audit results were checked for parity, not independently recomputed.'] };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const args = process.argv.slice(2); let study, probe;
    for (let i = 0; i < args.length; i += 2) {
      requireValue(args[i + 1], 'Missing argument value');
      if (args[i] === '--study' && !study) study = args[i + 1];
      else if (args[i] === '--source-probe' && !probe) probe = args[i + 1];
      else throw new Error('Usage: verify-study.mjs --study DIRECTORY [--source-probe FILE]');
    }
    requireValue(study, 'Usage: verify-study.mjs --study DIRECTORY [--source-probe FILE]');
    console.log(JSON.stringify(verifyDirectory(study, probe), null, 2));
  } catch (error) {
    console.error(JSON.stringify({ status: 'failed', reason: error.message })); process.exitCode = 1;
  }
}
