# Impeccable in the Selva harness

MADFAM standing rule: impeccable is used for any and all UI/UX work. Selva loads
this skill on every UI/UX task: front-end code, pages, components, styles,
layouts, forms, empty states, UX copy and design reviews. The upstream skill
text below is verbatim (pbakaus/impeccable `{{skill_tag}}`, npm
`impeccable@{{npm_version}}`, engine `{{engine_version}}`). This section says how
it maps onto a Selva worker; where the two disagree, this section wins.

## How the upstream skill maps onto Selva

- **Commands.** Upstream speaks of `/impeccable <command> <target>` and
  `$impeccable`. A Selva task names its command in the dispatch payload as
  `impeccable_command`, one of the {{command_count}} upstream commands:
  {{commands}}. When a task names one, that command's reference file follows
  this skill in your instructions; follow it. When it names none, treat the task
  as general design work under upstream Routing.
- **No launcher.** Selva workers do not run `scripts/impeccable context`, live
  mode, `generate`, `pin`, `hooks`, `doctor` or `npx impeccable`. Treat Setup
  step 1 as "Launcher unavailable": read the target repository's `PRODUCT.md`,
  `DESIGN.md` and `.impeccable/` config directly, and never invent missing
  context. Interviews (`init`, `document`) need a human: propose them in your
  result instead of blocking on them.
- **No roll API.** Choosing a new visual world (`reference/new-work.md`) calls
  impeccable.style; Selva workers do not. For a new surface or a replacement
  visual world, propose the directions in your result and let the operator pick.
- **Telemetry is always off.** Workers run impeccable with
  `IMPECCABLE_NO_TELEMETRY=1` and `DO_NOT_TRACK=1`. Never turn it on and never
  send project content to impeccable's services.

## Deterministic detector

The `impeccable_detect` tool runs the pinned detector (`impeccable detect
--json`: deterministic rules, no LLM, no network for files) on the task's changed UI files.
It is read-only on the workspace and forces telemetry off. In the coding graph it
runs automatically after the tests pass on a UI/UX task and before review; its
primary findings are fed back into the next implement iteration. In any other
flow, call `impeccable_detect` yourself before you report completion.

## Completion contract

1. The detector has run on every changed UI file before completion.
2. Fix primary findings. A primary finding you keep needs a one-line
   justification naming the rule, `file:line` and the reason (a pinned brief, a
   brand token the design system mandates, a false positive). Report each one in
   `ui_findings_justification` in the review JSON.
3. Advisory findings are listed, never counted, never blocking.
4. If the detector is unavailable, say "deterministic scan unavailable". Never
   claim a clean scan you did not run.

## Precedence

Upstream's own rule holds: the brief wins. Beyond it, these override this skill
wherever they are stricter: the target repository's AGENTS.md, DESIGN.md,
PRODUCT.md and design tokens; accessibility and legal requirements; and Selva's
own rules in its AGENTS.md. A detector finding never licenses breaking them.
