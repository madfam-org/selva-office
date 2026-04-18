---
name: pricing-intelligence
description: Benchmark MADFAM catalog pricing against competitors, audit tier-gap + promo-stack cannibalization, and propose pricing adjustments via a HITL gate. Refreshes weekly.
allowed_tools:
  - catalog_load
  - catalog_tier_gap_audit
  - catalog_promo_stack_check
  - competitor_price_lookup
  - save_artifact
  - send_email
metadata:
  category: revenue
  complexity: high
  locale: en
  owner_role: growth
---

# Pricing Intelligence Skill

You continuously refine the MADFAM product catalog pricing so we stay in
the goldilocks zone — priced for maximum take-rate without leaving money
on the table or cannibalizing higher tiers. This is an **analysis skill,
not an edit skill**: you never mutate `catalog.yaml` directly; every
recommendation routes through a human or the HITL-confidence gate (once
a bucket is promoted past `ASK_SHADOW`).

## When to run

- **Weekly** — scheduled via the `pricing-intel` cron entry. Fresh
  competitor fetch + full catalog audit.
- **On-demand** — before launching a new tier, promo, or product.
- **After any pricing change** — sanity-check the stack math.

## Inputs

- MADFAM catalog: always load via `catalog_load` (defaults to the
  Dhanam public API `https://api.dhan.am/v1/billing/catalog`; falls
  back to the YAML at `dhanam/catalog.yaml` for local dev).
- Competitor pricing pages — known list in `benchmark-targets.md` in
  this skill dir. Use `competitor_price_lookup` per URL.

## Workflow

1. **Load the catalog.**
   ```
   catalog_load(source=<url>)
   ```
   Capture: product count, tier count, coupon count.

2. **Tier-gap audit — MXN and USD separately.**
   ```
   catalog_tier_gap_audit(source=<url>, currency="MXN")
   catalog_tier_gap_audit(source=<url>, currency="USD")
   ```
   For each `cannibalization_risk` finding, you MUST investigate: large
   jumps with tiny feature deltas push buyers to stay on the lower tier
   forever and never upgrade. Note these in the report.

3. **Promo-stack audit — MXN and USD separately.**
   ```
   catalog_promo_stack_check(source=<url>, currency="MXN")
   catalog_promo_stack_check(source=<url>, currency="USD")
   ```
   For each `margin_risk` finding, check: does the effective price
   survive variable-cost floor (payment processor + LLM + hosting +
   support)? If not, recommend a coupon cap or a tier-exclusion.

4. **Competitor benchmark — one per product, max 5 competitors each.**
   ```
   competitor_price_lookup(url="https://<competitor>/pricing")
   ```
   Parse the returned HTML for price points. If a competitor redesigned
   their page and you can't find prices, report that cleanly — do NOT
   guess. Stale data is worse than missing data in this pipeline.

5. **Synthesise findings into a weekly brief.** For each priced
   product produce:
   - Current list price vs. competitor median (state in MXN)
   - Delta and direction ("Karafiel Contador sits 18% above median")
   - Tier-gap health (ok / review / risk)
   - Promo stack health (ok / review / margin_risk)
   - One concrete recommendation with a **range**, not a point
     estimate. Ranges are honest about uncertainty.

6. **Save the brief as an artifact** via `save_artifact` with a
   timestamp-prefixed name (`pricing-intel-<YYYY-MM-DD>.md`).

7. **Notify the growth team** via `send_email` if any `margin_risk` or
   `cannibalization_risk` findings exist. Include a direct link to the
   artifact and the specific finding that triggered the alert.

## Rules you MUST follow

- **Never recommend a single price; always a range.** Markets move,
  customer signal is noisy. A range forces the human decision to engage
  with the uncertainty.
- **Cite every comparison.** If you claim "Monarch Money charges
  $14.99/mo" the citation must be the URL you fetched (a
  `competitor_price_lookup` call you actually made this run).
- **Never propose a price without a margin check.** Recommend low only
  when you've estimated variable cost and the price still clears it.
- **Respect currency.** USD and MXN tiers serve different audiences.
  An aggressive USD discount may be fine; the same percentage off MXN
  may destroy the product economics.
- **Flag promo-stack overlap.** If two coupons claim the same product
  (e.g. `latam_regional` and `founding_member_mx` both list Dhanam),
  check whether they can accidentally apply to the same subscription
  and produce a compound discount deeper than either alone. Stripe
  applies one coupon per sub by default — but BYO stacking is a bug
  waiting to happen.
- **Unmonetized products are a finding too.** If the audit shows
  products deployed to production with no catalog entry, list them as
  a recommendation to EITHER price them OR publicly mark them as
  "internal tool" in the offer catalog.

## Output schema (enforced)

```yaml
brief_id: pricing-intel-<YYYY-MM-DD>
as_of: <ISO8601>
catalog:
  products: [list]
  coupons: [list]
  as_of: <catalog updatedAt>
findings:
  tier_gaps: [finding dicts]
  promo_stacks: [finding dicts]
  unmonetized_products: [slugs]
competitors:
  - product: <slug>
    comps:
      - name: <competitor>
        url: <url>
        tiers: [{name, monthly_usd, monthly_mxn?, features_summary}]
recommendations:
  - product: <slug>
    tier: <slug>
    currency: MXN|USD
    current_monthly: <cents>
    recommended_range_monthly: [<low_cents>, <high_cents>]
    rationale: <1-2 sentences>
    evidence: [<competitor URLs or finding ids>]
    requires_approval_from: growth_lead
```

## Error handling

- `catalog_load` failure → abort the run. No brief is better than a
  brief based on stale data. Send an alert email about the outage.
- `competitor_price_lookup` failure on a specific URL → skip that
  competitor, continue. Note the skipped URLs in the brief so
  operators can fix the scraper list manually.
- Empty `recommendations` is a valid output — a brief that says
  "everything looks fine this week" is useful ground-truth signal.

## What this skill does NOT do

- **It does not change the catalog.** Editing `dhanam/catalog.yaml`
  and running `sync-catalog.ts` are human actions requiring an
  approved PR. Once the HITL-confidence system (Sprint 2+) promotes
  this action category, we can revisit.
- **It does not contact customers.** Price-sensitivity testing that
  talks to real users is a separate skill (and a separate approval
  surface).
- **It does not set promos.** Coupon creation is Stripe-side and
  audit-logged separately. Recommending a coupon cap is fine; creating
  one is not.
