---
name: madfam-geometry-experience
description: "Build source-backed interactive explanations and improve geometry-factory workflows across MADFAM's solid, textile, sheet and experimental strand tools. Use for construction explainers, parameter/readout parity, fabrication evidence, or cross-platform geometry handoffs."
metadata:
  version: "0.5.0-draft"
  maturity: "local-draft"
---

# MADFAM Geometry Experience

Turn an evaluated design into a useful explanation, with traceable dimensions and honest check scope.
This is a local authoring skill draft, not a solver, production integration, public product name,
or manufacturing certification. Anatomy is an optional presentation backend.

## Start with the task and source

Read the target repository's applicable instructions. Determine the user's outcome: understand a
mechanism, edit fit, inspect a construction, prepare fabrication, or attach an existing accessory.
Use the smallest explanation that helps that outcome. Preserve the platform's normal workflow.

Read the selected manifest and native document/generator, not just a screenshot or catalogue name.
Record source repository, full commit, object path, resolved parameters, units and coordinate frame.
Inspect the evaluator's actual capabilities before promising a view or output. Source pins alone
do not lock the runtime, dependencies or generated geometry.

When working across MADFAM repos, read [ownership-and-adapters.md](references/ownership-and-adapters.md).
It gives routing and known seams; recheck the current schemas and repository instructions.

## Evaluate before explaining

Use the source owner's evaluator and validation. Do not execute an unreviewed uploaded generator
or HTML as part of an explainer. For trusted local generators, use the repository's established
isolated execution workflow. If evaluation is unavailable, deliver a source review or clearly
labelled schematic and list the missing outputs.

Keep these states distinct:

- **Literal construction:** geometry, part identities, dimensions and operation order come from
  the evaluated source. An exploded pose changes placement for explanation; it does not change
  source dimensions or claim an intermediate physical state.
- **Analogy:** an invented mechanism teaches a concept. Label it, and keep it out of dimensions,
  BOMs and fabrication exports.
- **Unsupported or unverified:** retain the missing fact. A plausible drawing does not fill it.

Bind each snapshot, readout, derived quantity and export to the same source/parameter digest.
Distinguish design dimensions, evaluated quantities, allowances and process compensation. Missing
closure, bend, contact, material or retention checks remain explicit. View controls select an
existing state; design edits go back through parameter validation and produce a new state.

## Choose and build the explanation

Keep accurate native geometry viewers available for model inspection. Use SVG/Anatomy where
primitives faithfully represent the explanation; use a native viewer or mesh adapter for detail
they cannot represent. Convert units and axes explicitly. Never reinterpret drawing pixels as mm.

Use stable physical part ids and operation ids. SVG subdivisions are render chunks, not extra
parts. A one-piece ring can have a one-piece explanation. Include labels, dimensions, anchors,
cut lengths, seam allowances or BOMs when they help the user's decision.

For Anatomy craft, dependencies and QA distinctions, read
[anatomy-and-evaluation.md](references/anatomy-and-evaluation.md). Preserve its model-first
discipline, depth checks and visual care. Avoid a mandatory part count or mandatory invented
machine in a literal product view. Motion explains an operation; it does not simulate material
physics unless an actual solver supplies that state.

Make geometry, selection, captions, accessible descriptions and numerical readouts share the same
evaluated state. Localize text separately from object ids. Use the host app's controls and theme.
Load explanations on demand and cache by instance digest. Measure payload and interaction cost;
do not ship a whole precomputed catalogue of views by default.

## Verify and deliver

Check the risks relevant to the change: invalid parameters, a changed non-default variant,
coordinate conversion, source/readout/export parity, keyboard operation, phone layout, reduced
motion and fallback. For moving or GPU views, check offscreen pause and teardown. Inspect actual
screenshots; do not infer visual quality from a clean console.

Separate results into input/lock integrity, native geometry, illustration ordering, browser
behavior and physical fabrication. Give counts and scope. Zero eligible samples means no evidence
for that check. Do not call an audit of recorded proxy shapes a manufacturing collision proof.

Two evidence adapters are available. The original helper supports the experimental three-strand
cuff `madfam.strand-study` / preview **0.1.0**:

```sh
node <skill-dir>/scripts/verify-study.mjs --study <trusted-study-directory>
node <skill-dir>/scripts/verify-study.mjs --study <trusted-study-directory> --source-probe <probe.json>
node --test <skill-dir>/scripts/verify-study.test.mjs
```

It reads data without executing the study: source/vendor hashes, snapshot/export/report parity,
crossing state, quantity arithmetic and positive audit coverage. It does not rerun the solver,
reaudit SVG, execute the source probe, or test browser behavior.

For the `jewelry-studio` native factory pilot, read
[native-factory-pilot.md](references/native-factory-pilot.md). Its ring, braid and paper/cord
workflows execute the owning native runners and produce real artifacts. Check an exported
`madfam.jewellery-instance` **0.1.0-draft** directory with:

```sh
python3 <skill-dir>/scripts/verify-bundle.py <instance-directory>
python3 <skill-dir>/scripts/test_verify_bundle.py -v
```

This checks disclosed source and parameter identities, physical quantities, native report/readout
parity, file hashes, private handoff and exact ZIP contents. It never executes the disclosed
generator or recomputes geometry. It preserves the unresolved mixed-schema and cord-tip interface
statuses. The profile is an experimental application format, not a ratified keystone contract.
No generic arbitrary-CAD, garment or folded-sheet adapter is claimed. Keep dependency closure
and unsupported assembly resolution visible.

For the local Fashion Cabinet placement consumer and Blueprint discovery planner, read
[cross-platform-pilot.md](references/cross-platform-pilot.md). Use those consumers to test the
handoff, rather than treating a producer's own fixture as integration evidence. The former
places a reference datum and reopens the pinned design; the latter produces policy-gated plans.
Neither establishes physical attachment, shared-contract ratification or production ingestion.

Deliver the working artifact or requested code, reproducible source identity, checks actually run,
and remaining limits. Reuse the host repository's documentation conventions. Skill authoring does
not authorize deployment, public gallery submission, production ingestion, or creation of a new
commons. Keep private projects and operational context outside public explainers.

For multi-family library growth and the 100-family Jewelry Studio evidence profile,
read [catalogue-evaluation.md](references/catalogue-evaluation.md). It adds exact
family counting, native export round-trip checks and an integrity-only catalogue checker.
