import test from 'node:test';
import assert from 'node:assert/strict';
import { canonical, digest, verifyDataset, verifySourceProbe } from './verify-study.mjs';

function fixture() {
  const event = { index: 0, generator: 1, before: ['A', 'B', 'C'], after: ['B', 'A', 'C'], over: 'A', under: 'B' };
  const audit = { physical_strands: 3, render_chunks: 12, overlapping_pairs_read: 4,
    wrong_order: 0, missing_shapes: 0, scope: 'Synthetic stored-record test only' };
  const s = { format: 'madfam.strand-study', version: '0.1.0', units: 'mm',
    parameters: { layout: 'cuff', inner_circumference_mm: 180, finishing_allowance_mm: 12, clearance_mm: 0.2, word: [1] },
    paths: ['A', 'B', 'C'].map(id => ({ id, points: [[0, 0, 0], [1, 0, 0]], centreline_length_mm: 1,
      cut_length_estimate_mm: 13, terminals: { start: [0, 0, 0], end: [1, 0, 0],
        start_lane: ['A', 'B', 'C'].indexOf(id), end_lane: ['B', 'A', 'C'].indexOf(id) } })),
    crossings: [event], end_permutation: ['B', 'A', 'C'],
    verification: { strands_read: 3, crossings_read: 1, crossing_order: true,
      clearance: { exact_segment_pairs_tested: 5, surface_lower_bound_mm: 0.3, scope: 'Stored test result, not independently verified' },
      terminal_state: 'Six open ends', unverified: ['All physical properties'] } };
  const d = { format: 'madfam.strand-study-preview', version: '0.1.0', source: { 'model.mjs': 'example' }, variants: [] };
  d.source_digest = digest(d.source);
  d.variants.push({ circumference: 180, snapshot: s, instance_digest: digest({ source_digest: d.source_digest, snapshot: s }),
    cuff: { svg: '<svg/>', audit }, frames: [{ svg: '<svg/>', audit: { ...audit },
      state: { completed: 1, total: 1, event, slots: ['B', 'A', 'C'], active: ['A', 'B'], readout: 'Step 1 of 1: A passes over B' } }] });
  return finalize(d);
}

function finalize(d) {
  const v = d.variants[0], s = v.snapshot;
  v.instance_digest = digest({ source_digest: d.source_digest, snapshot: s });
  const r = { source: d.source_digest, variants: [{ circumference_mm: 180, instance_digest: v.instance_digest,
    paths: s.paths.map(p => ({ id: p.id, centreline_mm: p.centreline_length_mm, cut_estimate_mm: p.cut_length_estimate_mm })),
    verification: structuredClone(s.verification), cuff_audit: structuredClone(v.cuff.audit),
    crossing_audits: v.frames.map(f => structuredClone(f.audit)) }] };
  return { d, r, e: new Map([[180, structuredClone({ source: d.source_digest, instance_digest: v.instance_digest, snapshot: s })]]) };
}
const check = f => verifyDataset(f.d, f.r, f.e);

test('known stored record has explicit positive coverage', () => {
  assert.deepEqual(check(fixture()), { variants_read: 1, strand_instances_read: 3, crossings_read: 1, stored_views_read: 2 });
});
test('changed source cannot keep stale source digest', () => {
  const f = fixture(); f.d.source['model.mjs'] = 'changed'; assert.throws(() => check(f), /Source digest/);
});
test('changed parameter cannot keep stale snapshot digest', () => {
  const f = fixture(); f.d.variants[0].snapshot.parameters.clearance_mm = 0.25; assert.throws(() => check(f), /Snapshot digest/);
});
test('export from another instance is rejected', () => {
  const f = fixture(); f.e.get(180).snapshot.paths[0].centreline_length_mm = 2; assert.throws(() => check(f), /Export\/preview/);
});
test('a report cannot silently alter a cut quantity', () => {
  const f = fixture(); f.r.variants[0].paths[0].cut_estimate_mm = 20; assert.throws(() => check(f), /quantity mismatch/);
});
test('consistent rehashing does not hide wrong allowance arithmetic', () => {
  const { d } = fixture(); d.variants[0].snapshot.paths[0].cut_length_estimate_mm = 20;
  assert.throws(() => check(finalize(d)), /allowance mismatch/);
});
test('contradictory over/under state is rejected', () => {
  const { d } = fixture(); d.variants[0].snapshot.crossings[0].over = 'C';
  assert.throws(() => check(finalize(d)), /Contradictory over\/under/);
});
test('selection, text and diagram state cannot drift', () => {
  const f = fixture(); f.d.variants[0].frames[0].state.readout = 'Step 1 of 1: B passes over A';
  assert.throws(() => check(f), /Text readout/);
});
test('render chunks cannot masquerade as physical strands', () => {
  const { d } = fixture(); d.variants[0].cuff.audit.physical_strands = 12;
  assert.throws(() => check(finalize(d)), /Physical parts\/render chunks/);
});
test('zero audit reads cannot count as painter evidence', () => {
  const { d } = fixture(); d.variants[0].cuff.audit.overlapping_pairs_read = 0;
  assert.throws(() => check(finalize(d)), /Zero sampled/);
});
test('unknown format is unsupported', () => {
  const f = fixture(); f.d.format = 'mixed-assembly'; assert.throws(() => check(f), /Unsupported preview/);
});
test('manufacturing limitations cannot disappear', () => {
  const { d } = fixture(); d.variants[0].snapshot.verification.unverified = [];
  assert.throws(() => check(finalize(d)), /limitations/);
});
test('canonical hash is stable for key order and refuses nonfinite values', () => {
  assert.equal(digest({ b: -0, a: 1 }), digest({ a: 1, b: 0 }));
  assert.throws(() => canonical({ value: Infinity }), /finite plain JSON/);
});
function probe() {
  const source = { repository: 'https://github.com/madfam-org/solid-hyperobjects', commit: 'a'.repeat(40),
    path: 'jewelry-blank', engine: 'test-engine@source-only', parameters: { size: 7 }, content_sha256: 'b'.repeat(64) };
  return { status: 'source-lock-only', geometry_rendered: false,
    references: [{ source: { ...source, instance_digest: digest(source) }, scope: 'Generator not executed' }],
    current_assembly_allowed_cartridge_commons: ['solid'], mixed_assembly_status: 'unsupported-by-current-ASM-1-schema' };
}
test('source lock integrity preserves unexecuted and incomplete-runtime status', () => {
  const result = verifySourceProbe(probe());
  assert.equal(result.references_read, 1); assert.equal(result.geometry_rendered, false);
  assert.equal(result.source_bytes_rechecked, false); assert.equal(result.runtime_closure_verified, false);
});
test('source mutation invalidates instance lock', () => {
  const p = probe(); p.references[0].source.parameters.size = 8; assert.throws(() => verifySourceProbe(p), /digest mismatch/);
});
test('floating commit and traversing paths are refused', () => {
  const p = probe(); p.references[0].source.commit = 'main'; assert.throws(() => verifySourceProbe(p), /immutable/);
  const q = probe(); q.references[0].source.path = '../other'; assert.throws(() => verifySourceProbe(q), /Unsafe source/);
});
test('a source-only probe cannot promote itself to a rendered assembly', () => {
  const p = probe(); p.geometry_rendered = true; assert.throws(() => verifySourceProbe(p), /unexecuted/);
  const q = probe(); q.mixed_assembly_status = 'supported'; assert.throws(() => verifySourceProbe(q), /no mixed assembly/);
});
