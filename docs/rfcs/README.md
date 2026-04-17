# RFCs

Design docs for non-trivial changes. Each RFC gets a number, a status,
and lives as a single markdown file in this directory.

## Index

| # | Title | Status |
|---|---|---|
| [0001](./0001-onboarding-improvements.md) | Onboarding improvements informed by category benchmark | Draft |

## When to write one

- Any proposal that touches onboarding, auth, or consent surfaces.
- Any proposal that would change a cross-service contract (Janua,
  Dhanam, Karafiel, Selva's `/v1` inference proxy).
- Any proposal that adopts or rejects a competitor pattern after
  deliberate comparison.

Small bugfixes, single-service refactors, and product tweaks do not
need an RFC — open a PR with a clear description instead.

## Status lifecycle

`Draft` → `In review` → (`Accepted` | `Rejected` | `Superseded`)

Accepted RFCs may still receive amendments; use a new RFC that marks
the original superseded rather than editing history.
