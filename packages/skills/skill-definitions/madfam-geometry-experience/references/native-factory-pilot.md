# Native factory pilot: jewelry-studio

Use this reference when the user's task involves the local `jewelry-studio` pilot or its design
bundles. The repository name was owner-authorized as a working name on 2026-10-15. It does not
establish a public brand, hosts, deployment or fourth commons.

## What actually evaluates

| Workflow | Canonical source and evaluator | Actual output and check scope |
|---|---|---|
| Ring | `solid-hyperobjects/jewelry-blank`, Yantra4D restricted CadQuery runner | STEP, STL and native B-Rep projection; solid validity/body count, measured cylindrical bore, watertight mesh |
| Braid | Experimental local ordered-strand kernel; native `solid-hyperobjects/cord-end` findings | Distinct paths/crossings/cut lengths, closed strand meshes, six independently placed tips; scoped separation and illustration ordering |
| Paper and cord | `sheet-hyperobjects/paper-beads` through Pliego; `soft-hyperobjects/cord-end-notion` through FC; solid finding through Yantra4D | Native sheet document/target GLB/cut files, native cord SVG/DXF/PDF and solid STEP/STL; joining and mixed ASM-1 remain unresolved |

Material study selections record appearance and intent. A wood and silver band with equal source
parameters have equal geometry; neither receives uncalibrated process compensation.

The mixed study deliberately records a real seam: FC adds the nominal tip length to cord cut
quantity, while the solid tip has a shorter blind bore. The current pilot runs 50 native STEP
centreline point queries to measure the axial stop: 11 mm for a 12 mm tip with a 1 mm wall,
against the FC guide's 12 mm reserved per end. The resulting 1 mm overrun is recorded in
`interface-report.json`. This probe does not establish radial, crimp or retention compatibility.
Valid independent components do not prove
a compatible joining recipe. Preserve `mixed-ASM-1: unsupported` and
`cord-tip-length-semantics: unverified` for this profile version.

## Local authoring commands

After reading the repo's `AGENTS.md`, use its documented checkouts and existing native runtime
environments. The working directory is the repository root:

```sh
python3 factory.py ring --params '{"ring_size":9.5,"material":"wood-study"}'
python3 factory.py braid --params '{"inner_circumference_mm":180}'
python3 factory.py mixed --params '{"style":"bicone","cord_dia":2}'
npm test
python3 server.py --port 8910
```

The build prints its `instance_digest`; its files live in `cache/<digest>/`. `sources/` holds
ignored pinned read copies, not a new source commons. Do not point the generator runner at
unreviewed uploads. The local server binds loopback and has no upload, publication or live feed.

The draft cache identity includes the application evaluation revision as well as source pins
and parameters. It is not a canonical cross-platform commons object id. Source object identity,
resolved component instance identity and exported document/artifact digests are separate fields.
Do not publish these temporary cache ids as a ratified discovery identity scheme.

## Bundle adapter

`verify-bundle.py` reads `instance.json`, its declared files and `design-bundle.zip`. It verifies:

- document and request digests using this draft's sorted compact UTF-8 Python JSON serialization;
- full source/engine pins, source-byte disclosure, attached source licence and resolved parameters;
- actual-file hashes and sizes, unique BOM identities, quantities/units and CSV parity;
- ring bore/readout, braid cut-length/body-count, and sheet/cord quantity parity with stored reports;
- measured insertion-report/guide/readout parity when the native axial probe is present;
- positive counts for passed checks, explicit limits, a private handoff and exact ZIP membership.

The helper does not authenticate authorship, fetch Git objects, rerun an evaluator, independently
measure a B-Rep, reaudit SVG, test the browser or qualify manufacturing. A coordinated rewrite of
all records is outside its integrity model. It intentionally rejects a profile claiming complete
runtime closure or manufacturing qualification, since those claims are not established here.

The local integration suite runs real native evaluators; the helper's 15 small unit tests use
synthetic stored-record fixtures and must not be reported as additional geometry execution.
Keep browser evidence separate. Use actual desktop/phone screenshots and a no-WebGL run.

## Handoff boundary

The exported accessory reference is private and retains the evaluated parameters and pins.
Ring and braid references declare a row-major mm transform from Z-up to Y-up; the unresolved
mixed composition carries no attachment transform. Its editor route reopens the exact local
instance. The anchor remains unassigned until explicitly mapped. The local Fashion Cabinet
consumer now imports supported references, records a garment/body datum and reopens that instance;
it does not import a jewellery mesh or prove a physical attachment. See
[cross-platform-pilot.md](cross-platform-pilot.md) for the producer/consumer checks.

The producer's original in-memory discovery fixture is a small unit fixture. The Blueprint-owned
offline planner independently checks source identities, separate assembly/component licensing,
privacy, dependency reuse and withdrawal. It makes no production network call. Blueprint's live
connector, source policy and persisted identity migration remain separate work. Never turn an
offline public test fixture into actual publication of a user's private design.
