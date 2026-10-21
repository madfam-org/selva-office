# Anatomy craft, evidence and comparative evaluation

## Upstream relationship

The evaluated upstream skill is [Anatomy](https://skills.wheresryan.sh/anatomy), source
[`wheresryan22/anatomy`](https://github.com/wheresryan22/anatomy/tree/bc943e40c59998be5da61f9d39c6a983b1116099),
commit `bc943e40c59998be5da61f9d39c6a983b1116099`, MIT licensed. The optional kit and QA scripts
are upstream dependencies, not bundled with this skill. These MADFAM instructions and the
integrity helper are original. Do not silently fetch or execute an unpinned updated kit.

When a trusted pinned checkout is available, read its `SKILL.md` and the relevant kit API/example.
Its source workflow requires Node >=20.10 and Chrome/Chromium for browser QA. Inspect actual
dependencies before running it. Keep the MIT copyright and licence with substantial copied code,
and record upstream commit plus file hashes. This skill is usable without Anatomy: choose the
host platform's viewer or a faithful static view when appropriate.

The separate [anatomy-figures repository](https://github.com/wheresryan22/anatomy-figures/tree/d4590e39369d813cd98450f6f6407634a25ad85a)
was inspected at `d4590e39369d813cd98450f6f6407634a25ad85a` (package 0.1.0). Its figures are
educational components; their presentation props are not a CAD evaluation API. Recheck current
exports, React requirements and theme support before integration.

## Craft worth retaining

Make the object explain the mechanism. Build a pure evaluated model before drawing; use
purposeful parts, consistent shading, deliberate depth ordering, meaningful motion and coherent
camera composition. Use one accent or multiple material/strand colours according to the task.
Give abstract concepts a strong literal analogy when that is the requested explanation.

For real designs, prioritize construction fidelity. Do not invent parts to meet Anatomy's
40-part Figure target, hide useful measurements to avoid labels, or turn a real part into an
unrelated teaching machine. Distinguish explanatory explode distance from assembled clearances.
Tube texture is not strand topology; a spring animation is not a rod/contact simulation.

Anatomy's recorder and audit must record the actual rendered geometry, not convenient proxies
that differ from it. Resolve painter order at each supported view/pose and report sample counts.
Clipping, taper and thin features need explicit coverage. The optional texture-line audit's
zero eligible lines is an inapplicable check, not a pass. Arbitrary B-Rep cannot be faithfully
recreated by choosing a visually similar lathe profile.

## Keep five evidence layers separate

| Layer | Useful evidence | Does not establish |
|---|---|---|
| Source and lock integrity | Exact commit, parameters, content/dataset hashes, runtime closure status | Correct evaluated geometry |
| Native geometry | Engine tests, measured dimensions, valid contours/topology, solver checks | Material/process performance |
| Illustration | Recorded shapes, sampled depth/clearance, correct state and readout | Global physical collision freedom |
| Browser behavior | Keyboard, phone, reduced motion, fallback, cleanup, payload and measured timing | Geometric or fabrication accuracy |
| Fabrication | Process-specific checks, maker round-trip and measured results | Universal suitability for other processes |

The bundled `scripts/verify-study.mjs` checks integrity and stored-data parity for one local
study format only. Its report deliberately says `geometry_recomputed: false`,
`illustration_reaudited: false`, and `browser_exercised: false`. Run the study's model suite,
build/audit pipeline and browser QA separately when their evidence is required.

`scripts/verify-bundle.py` adds stored-evidence checks for the native factory pilot described in
[native-factory-pilot.md](native-factory-pilot.md). Its source disclosure and export checks
complement the actual runner and browser suites; they do not replace either one.

## Evaluation before claiming superiority

Use the same source, task, time budget and environment for baseline Anatomy and this skill.
Keep the upstream pin fixed for a trial; record all local modifications. Review outputs without
revealing which workflow produced them when practical. Include:

1. A three-strand cuff at two fits: crossing identity, true cut length, six open ends and invalid
   parameter/collision rejection. Change source after rendering to test stale-output detection.
2. A one-piece ring: real dimensions, material/process assumptions, no invented hardware, a
   non-default size and the owning evaluator's actual export.
3. A paper bead: source sheet/cut geometry, roll sequence and preserved source dimensions.
4. A textile accessory attachment: actual seam/anchor data, pinned finding, editor handoff.
5. A mixed construction whose current schema cannot resolve every source: truthful unsupported
   status and a useful limited preview.
6. An abstract mechanism explanation, where Anatomy's visual storytelling is a strong baseline.

Score correct source and quantities, reproducibility, useful unsupported-case handling, task
completion, clarity, accessibility, payload and interaction cost. Record author effort separately.
An attractive screenshot does not outweigh a false manufacturing claim; an integrity checker
does not prove the explanation is understandable. Set numeric performance targets after a
measured baseline. The first strand proof alone cannot establish broad superiority.

## Adoption sequence

Keep the skill independently versioned from runtime renderers and solvers. Prove the strand
adapter, then one solid and one sheet/textile consumer before extracting a shared package or
ratifying a shared snapshot schema. Capture useful fixes upstream where compatible; avoid
maintaining a wholesale fork of Anatomy merely to change branding. Public naming, licensing and
distribution of a MADFAM skill remain decisions outside this local draft.
