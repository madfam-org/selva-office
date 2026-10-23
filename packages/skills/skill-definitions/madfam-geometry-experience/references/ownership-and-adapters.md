# Source ownership and adapter routing

These are routing hints, checked against the MADFAM checkouts on 2026-10-15. They are not a new
registry or schema. Read current repository instructions, manifests and supported formats.
For private operational rulings, consult `internal-devops` when available; never copy its private
topology or operational details into a public deliverable.

## Route by construction mechanics

| Native construction | Public source owner | Evaluator / editing experience |
|---|---|---|
| Solid geometry, profiles, boolean/loft/sweep features | `solid-hyperobjects` | Yantra4D and the object's declared runner |
| Drafted textile panels, seams, cut/sew operations | `soft-hyperobjects` | Fashion Cabinet and the object's declared runner |
| Developable cut/fold/roll constructions | `sheet-hyperobjects` | Pliego and the object's declared runner |
| Ordered strand paths, crossings, lengths and terminations | No fourth commons established by this skill | Experimental construction evaluator, with an explicit capability statement |

Material does not select the kernel. A wooden ring may be solid; folded metal may be sheet;
a woven cord is not automatically a cut/sew pattern. A thin printable feature alone is not a
developable sheet construction. Read the object mechanics and declared schema.

Use existing canonical sources, including reusable findings, clasps, blanks, beads and notions.
An accessory category does not justify copying generators into a jewellery commons or platform.
A public mixed recipe follows the ruled parent/source ownership and supported reference schema.
Keep a rootless collection as references; propose unresolved ownership instead of inventing it.

## Adapter inputs and output separation

An adapter needs actual evaluated geometry or native operation data, full source identity,
resolved parameters, units, source frame and stable ids. A proposed portable snapshot could carry
representable primitives/mesh references, interface frames, poses/steps, metrics with provenance,
captions and scoped check results. This is a design direction, not a canonical keystone format.

Keep these concerns in their owning repositories:

- `hyperobjects-spec`: ratified shared contracts, schemas and conformance fixtures. Browser
  components and solver implementations belong with their runtime owners.
- Commons: canonical public object source, native operations, source articles and object evidence.
- Platforms: evaluation adapters, domain editing, validation, accurate viewers and UX.
- Shared browser package: only after two real consumers prove the same interface.
- Authoring skill: orchestration, routing, scoped claims and repeatable local QA.

Do not add a service to render a small explanatory SVG. Do not make platform runtimes depend on
each other. A renderer's absence is a capability gap, not permission to guess geometry.

## Known seams to recheck

- At the inspected `hyperobjects-spec` commit
  `70fe8213de20bc9a699b2bde2c32ee0b02a6d52d`, ASM-1's `cartridgeSource.commons` permits only
  `solid`. Reader code in another repo is not evidence that a mixed schema is supported.
- Anatomy uses z-up; Fashion Cabinet and Pliego use y-up in their native viewers. Declare an
  actual transform, scale and handedness for the selected source, not just an axis label.
- A source lock with an engine source commit still needs runtime and library closure for a
  reproducible evaluator. Hashing manifest/generator bytes does not run or validate them.
- Material shaders communicate appearance. Stone fit, wood grain, casting compensation, seam
  allowances and wire springback require their own data and appropriate checks.
- A source-derived BOM distinguishes canonical component type from assembled instance count.
  Render chunks, duplicate previews and alternate representations do not increase quantities.

## Handoffs

Fashion Cabinet should retain an immutable accessory reference, resolved parameters, anchor and
transform, and open the owning editor for a design change. Editing an outfit should not silently
update a pinned accessory or copy its generator.

Blueprint previews should resolve through the supported public source feed and correct editor
handoff. Preserve canonical identities, dependency edges, licence/provenance and withdrawal
policy. A skill invocation does not authorize production ingestion or publication. Private or
unlisted designs do not become public because an explanation was generated.

Cross-medium derivations, such as origami jewellery or a garment turned into a rigid print,
preserve their source lineage and record lost mechanics. Geometry likeness alone does not
preserve foldability, drape, fit, strength or material behavior.

## Skill distribution and Selva

Selva already has first-party skill definitions in `selva-office/packages/skills/skill-definitions`
and separately controlled community skills. At inspected commit
`2d855391ccf547d2078fd377ecfa80e21dc30c58`, its `SkillRegistry` lazily loads `SKILL.md` and defaults
to tenant audience; production execution still needs the existing tool/capability gates.
This is the first repository home to evaluate for a MADFAM-owned definition. Do not assume a new
skill repository or broaden the community-skill allowlist merely to distribute it.

The local draft parses and activates in that registry without executing a worker. Its tool list
is empty. Codex's frontmatter convention `allowed-tools` and Selva's typed field `allowed_tools`
are different spellings; Selva's inspected parser has no alias. Adding one field to portable
prose therefore does not establish runtime permission. Before a Selva release, explicitly map
and test least-privilege tool bindings, artifact containment, audience and worker isolation.
Keep one maintained definition with tested distribution metadata rather than divergent copies
per coding agent. Registering this local draft in a live registry is a separate action.
