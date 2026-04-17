# RFC 0001 — Onboarding improvements informed by category benchmark

- **Status**: Draft
- **Author**: platform
- **Created**: 2026-04-17
- **Related**: PR #26 (voice-mode + consent ledger)

## Summary

Three additive onboarding changes informed by a benchmark of Selva against
the nine virtual-office platforms on [ro.am/virtual-office-platform][roam].
The benchmark produced one clear finding — our consent step is a category
outlier, defensible on legal grounds — and three small gaps worth closing
so the non-differentiating parts of onboarding stop costing us friction.

- **R1** — Add a Terms + Privacy checkbox to the voice-mode consent screen.
- **R2** — Add a non-blocking "Next steps" checklist inside `/office`.
- **R3** — Add an email-code auth fallback for when Janua SSO is unreachable.

Each is independent and can ship separately. None changes the behaviour
of the voice-mode gate shipped in PR #26.

[roam]: https://ro.am/virtual-office-platform

## Benchmark findings (condensed)

Full research lives in the companion thread; the three findings this RFC
acts on:

1. **We are the only platform with a consent event before AI outbound** —
   none of Roam, Gather, Kumospace, Sococo, Teamflow, oVice, Spot, SoWork,
   or WorkAdventure does this. Keep it.
2. **Sococo is the only platform with a legal-acceptance checkbox during
   signup** — the rest rely on passive ToS footers. Category is moving
   toward explicit acceptance, LFPDPPP 2025 and GDPR Art.7 both reward it.
3. **SoWork's post-onboarding checklist is measured to improve D7
   retention** — the pattern is cheap and widely adopted.

## R1 — ToS + Privacy checkbox on voice-mode screen

### Motivation

The typed-phrase confirmation in PR #26 captures affirmative consent to
the voice-mode *clause*. It does not capture acceptance of the platform
ToS + Privacy Policy. Sococo is the only comparator that handles this
cleanly — a checkbox on account creation. Adding the same pattern to our
voice-mode screen keeps legal acceptance on a single page rather than
leaving it as a passive footer.

### Proposal

- Add a required checkbox above the "Confirm & enter office" button:
  > ☐ I agree to the [Terms of Service][tos] and [Privacy Policy][priv].
- Record acceptance as a second row in `consent_ledger` with
  `mode = "terms_privacy"` and a separate `clause_version` string
  (`terms-v1.0`). Same signature scheme, same append-only guarantee.
- The `/settings/outbound-voice` change endpoint does **not** re-prompt
  for ToS (already accepted). Only triggered on first-run onboarding or
  when `terms-v1.x` version bumps.

### Out of scope

- Supporting jurisdictional variants (EU vs US vs MX ToS). Handled by
  clause-version bumps later.
- ToS / Privacy Policy content itself — product + legal own that.

[tos]: https://selva.town/legal/terms
[priv]: https://selva.town/legal/privacy

## R2 — Post-onboarding "Next steps" checklist

### Motivation

After voice-mode selection the user lands in `/office` with nothing
obviously actionable. SoWork's published onboarding guide attributes a
measurable D7 retention lift to a 4–5 item checklist surfaced on the
first few visits. Our office already has most of these integrations —
they just aren't discoverable until the user explores the HUD.

### Proposal

A non-blocking pinned card in the top-left of `/office` on first visit
with 5 items. Each item marks complete on the relevant action.

1. **Invite your team** — one-click invite link generator (already in
   `/admin/users`, surface it here).
2. **Connect your calendar** — opens `CalendarPanel` in connect flow.
3. **Choose an avatar** — opens `AvatarEditor` (today an auto-shown
   first-visit modal; make it a checklist item so it can be skipped
   once and revisited).
4. **Run a test task** — opens `TaskDispatchPanel` pre-filled with a
   sample description.
5. **Add your voice mode to CRM playbooks** — links to playbook
   marketplace filtered by "voice-mode-aware" tag.

### Persistence

Checklist state is per-user, not per-org, stored in a small
`onboarding_checklist` JSON column on the users table (or Redis with
30-day TTL — cheaper, but loses state across devices). Prefer DB column.
Dismissed or fully-complete checklists collapse into a small badge.

### Events

Emit `onboarding.checklist.item_completed` per item for funnel analytics.

### Out of scope

- Gamification (XP, badges). Adds cost, no evidence it moves retention
  for B2B tools.
- Forced-flow variant ("you must complete all items to leave the office").
  Category norm is non-blocking; forced would be hostile.

## R3 — Email-code auth fallback

### Motivation

Current auth paths are (a) Janua SSO or (b) dev bypass. If Janua is down
or misconfigured for a new tenant, users hit a dead-end. Roam's 6-digit
email code pattern is the simplest functional fallback in the category
and keeps us from being worse-than-Roam on availability.

### Proposal

- New endpoint `POST /api/v1/auth/email-code/request` — accepts email,
  enqueues a 10-minute 6-digit code via `SendEmailTool` (system
  context — bypasses voice-mode gate with a `system` mode that cannot
  be set by tenants).
- New endpoint `POST /api/v1/auth/email-code/verify` — accepts email +
  code, mints a short-lived Janua-compatible JWT with scoped claims
  (`roles: ["member"]`, no admin). Stored in the same `janua-session`
  cookie so downstream code needs no changes.
- Feature-flagged via `AUTH_EMAIL_CODE_ENABLED` env var. Default off in
  production until Janua team reviews threat model.
- Rate-limited at 5 requests / email / hour via existing
  `MessageRateLimiter`.

### Threat model

- Code brute-force: 6-digit code = 10^6 entropy + 5 attempts/hour + 10
  min TTL ≈ acceptable for low-privilege fallback. Lock account after
  5 failed verifies.
- Email interception: same risk profile as Roam, Gather, SoWork — all
  use similar codes. Documented in security model.
- Bypass of Janua SSO for SSO-mandated tenants: **DO NOT** allow code
  login when `tenant_configs.janua_connection_id IS NOT NULL`. Refuse
  with explicit error directing user to the SSO IdP.

### Out of scope

- Passkeys / WebAuthn. Separate, bigger RFC. Janua should own that.

## Rollout plan

| Item | Effort | Risk | Owner |
|---|---|---|---|
| R1 checkbox | ~1 day | Low | Frontend |
| R2 checklist | ~1 week | Low | Frontend + 1 backend schema change |
| R3 email code | ~1 week | Medium (security review) | Janua liaison + backend |

R1 can merge standalone. R2 and R3 are independent and can parallelize.
None should merge before PR #26 (voice-mode) lands.

## Alternatives considered

- **Adopt Gather's template-picker** — rejected. Irreversible
  step-1 decisions are user-hostile and we have one default office map
  that works for every org.
- **Adopt Teamflow's CSM-assisted onboarding** — rejected. Does not
  scale for product-led motion and conflicts with the self-serve
  positioning.
- **Adopt WorkAdventure's forced avatar/cam/mic gate** — rejected.
  Category is actively moving away from this (oVice removed it in
  Jan 2026).

## Open questions

1. Should R1 treat ToS acceptance as tenant-level (one admin accepts for
   the org) or user-level (every member accepts on first login)? Both
   have legal precedent. Default draft proposes user-level because the
   `consent_ledger` is already user-keyed.
2. For R2, does the "run a test task" item count against the tenant's
   `max_daily_tasks` quota? Default: yes, but it's 1 task out of 100.
3. R3 threat model review — does Janua want to own the email-code flow
   directly (and Selva just consumes the IdP) rather than implementing
   it in nexus-api? Preferred long-term answer.

## Non-goals

- Redesigning the voice-mode consent flow (done in PR #26).
- Building analytics dashboards for onboarding funnel (separate RFC).
- Adding localization beyond Spanish (every item here should be
  translation-ready but translations land separately).
