---
name: dns-migration
description: Migrate a domain's authoritative DNS from Porkbun to Cloudflare, then configure the intended service on the Cloudflare side — typically a full-domain 301 redirect or a proxied record into the MADFAM cluster. Handles zone creation, NS delegation, DNS records, Page Rules, and cleanup of legacy Porkbun URL forwarding.
audience: platform
allowed_tools:
  - porkbun_list_domains
  - porkbun_get_nameservers
  - porkbun_update_nameservers
  - porkbun_list_dns_records
  - porkbun_list_url_forwarding
  - porkbun_delete_url_forwarding
  - porkbun_domain_health_check
  - cloudflare_list_zones
  - cloudflare_create_zone
  - cloudflare_create_dns_record
  - cloudflare_list_dns_records
  - cloudflare_create_redirect_rule
  - cloudflare_list_page_rules
metadata:
  category: infrastructure
  complexity: medium
  reversibility_cost: high
---

# DNS Migration Skill (Porkbun → Cloudflare)

You are the MADFAM infrastructure agent responsible for moving a domain's
authoritative DNS from its Porkbun defaults onto the Cloudflare account,
then standing up whatever the domain is actually for.

Every domain lands on this skill in one of three shapes:

1. **Redirect-only** (nuitone.com → nuit.one, enclii.com → enclii.dev,
   madfam.org → github.com/madfam-org, etc.). End state: CF zone with an
   apex + wildcard proxied A record pointing at `192.0.2.1`, plus a
   wildcard Page Rule forwarding `*<domain>/*` to the target with 301.
2. **Proxied service** into the MADFAM cluster. End state: CF zone with
   CNAME or A records resolving to a Cloudflare Tunnel ingress pod.
3. **External SaaS** (Vercel, Railway, etc.). End state: CF zone with
   the provider's A/CNAME targets. The user owns this shape today — we
   only move DNS authority to CF so future tunnel cutover is painless.

## Invariants

- **Never touch `*.madfam.io` via this skill.** Those zones live on CF
  already; this skill is specifically about registrar-level migration.
- **Always check `cloudflare_list_zones` first** — the zone may already
  exist, in which case skip to Step 2.
- **NS pairs are per-zone.** CF assigns different nameserver pairs to
  different zones (`chin/woz`, `gene/javier`, `gloria/sonny`, …). Use the
  exact pair returned by `cloudflare_create_zone` (or `list_zones`) when
  calling `porkbun_update_nameservers`.
- **The apex + wildcard A records must be proxied** (`proxied=true`) for
  Page Rules or any other CF-edge feature to fire. `192.0.2.1` is a valid
  RFC-5737 placeholder for the A value when redirecting — CF's proxy
  intercepts the request before the origin is ever dialled.
- **Delete the Porkbun URL forwarding last.** It's load-bearing until the
  CF Page Rule is live; if you remove it before NS propagation completes,
  the domain serves nothing for a window.

## Step-by-step flow

### Step 1 — Verify the starting state

```python
health = await porkbun_domain_health_check()
porkbun_ns = await porkbun_get_nameservers(domain=d)
cf_zones = await cloudflare_list_zones(name=d)
url_fwds = await porkbun_list_url_forwarding(domain=d)
```

If `cf_zones.data.zones` already contains the domain, skip Step 2 and
reuse that zone id. Otherwise:

### Step 2 — Create the CF zone

```python
zone = await cloudflare_create_zone(domain=d)
zid = zone.data.zone_id
ns_pair = zone.data.name_servers  # list of 2 strings
```

The zone boots in `pending` status until NS propagation lands.

### Step 3 — Create the apex + wildcard proxied A records

```python
await cloudflare_create_dns_record(
    zone_id=zid, type="A", name=d,
    content="192.0.2.1", proxied=True,
)
await cloudflare_create_dns_record(
    zone_id=zid, type="A", name="*",
    content="192.0.2.1", proxied=True,
)
```

For service (non-redirect) shapes, point at the real target instead:

- Cloudflare Tunnel: `CNAME` to the tunnel domain + `proxied=true`.
- External SaaS: `A` / `CNAME` to the provider target (Vercel `76.76.21.21`,
  Railway `*.up.railway.app`, etc.) + `proxied=false`.

### Step 4 — Create the redirect Page Rule (redirect-only shape)

```python
await cloudflare_create_redirect_rule(
    zone_id=zid, domain=d, target="https://<target>", status_code=301,
)
```

The rule matches `*<domain>/*` and forwards to `<target>/$2`, preserving
path + query. It works for apex AND every subdomain.

### Step 5 — Delegate NS at the registrar

```python
await porkbun_update_nameservers(domain=d, nameservers=ns_pair)
```

Propagation typically lands inside an hour but CF marks the zone active
only when it observes the new NS answering queries.

### Step 6 — Clean up the Porkbun URL forwarding

Once CF serves the redirect, the Porkbun forward is redundant and
conflicts with CF for DNSSEC + analytics.

```python
for f in url_fwds.data.forwards:
    await porkbun_delete_url_forwarding(
        domain=d, forward_id=f["id"],
    )
```

### Step 7 — Verify

Poll the CF zone status until it flips to `active`:

```python
for _ in range(12):  # ~6 min
    z = await cloudflare_list_zones(name=d)
    if z.data.zones[0]["status"] == "active":
        break
    await sleep(30)
```

Smoke the redirect:

```bash
curl -s -o /dev/null -w "%{http_code} → %{redirect_url}\n" "https://<domain>"
# expect: 301 → <target>/
```

## Known pitfalls

- **HTTPS 000 immediately after setup.** CF issues the edge cert via
  ACME; this can take minutes. `http://` works immediately, `https://`
  follows.
- **Rulesets API returns "Authentication error."** The platform's
  `cloudflare-api-credentials` token does NOT carry `Zone Rulesets:Edit`
  scope. Use `cloudflare_create_redirect_rule` (Page Rules) instead — it's
  functionally equivalent for full-domain 301s.
- **`gloria/sonny`, `chin/woz`, `gene/javier`…** CF uses a pool of NS
  pairs; different zones get different pairs. Don't hardcode them across
  domains; always use whatever `create_zone` returned.
- **Zone already exists but with a different account.** If `create_zone`
  returns `1061` it's already been registered elsewhere. Don't force —
  escalate to HITL; reclaiming a zone from another account is a signed
  operation outside the scope of this skill.

## Output

Return a structured report:

```yaml
domain: <d>
zone_id: <zid>
assigned_ns: [<ns1>, <ns2>]
old_ns: [<old1>, <old2>, ...]
records_created:
  - {type: A, name: <d>, content: 192.0.2.1, proxied: true}
  - {type: A, name: '*', content: 192.0.2.1, proxied: true}
page_rule_id: <pr>
porkbun_forwards_deleted: [<id1>, ...]
status: active | pending_propagation
verification: <curl output>
```

## Reversibility

This operation is **high reversibility cost**. To roll back:

1. `porkbun_update_nameservers` with the original NS pair (recorded in
   the `old_ns` field of the skill output).
2. Re-create the Porkbun URL forward if it was deleted.
3. Delete the CF zone via the dashboard (no API delete tool surfaced
   yet — deliberate; zone deletion is a signed op).

Wait for NS TTL (typically 24h) before expecting full rollback. Because
of the long TTL, this skill should be HITL-gated at `ASK_QUIET` or
stricter for domains with active traffic.
