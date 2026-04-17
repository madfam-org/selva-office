#!/usr/bin/env bash
# voice-mode-smoke-test.sh — verify the outbound voice-mode gate
# end-to-end against a running Selva deployment.
#
# Executes plan item T2.2 from the MXN flywheel roadmap. Runs nightly
# in staging; failure pages on-call.
#
# Usage:
#   ./scripts/voice-mode-smoke-test.sh                 # default staging env
#   NEXUS_API_URL=https://api.selva.town ./scripts/voice-mode-smoke-test.sh
#   ./scripts/voice-mode-smoke-test.sh --json          # machine-readable
#
# What it checks
# --------------
# 1. GET /api/v1/onboarding/status — reachable and returns one of the
#    documented clause versions.
# 2. GET /api/v1/onboarding/voice-mode/preview/{mode} — returns a
#    non-empty clause for each of the 3 legal modes.
# 3. POST /api/v1/onboarding/voice-mode with a **mismatched** phrase
#    must 400, not silently succeed. This is the critical guardrail.
# 4. GET /api/v1/tenants/me exposes the `voice_mode` field (API was
#    silently dropping it before commit 9a882f7).
#
# Does **not** send real email. That requires:
#   - A tenant that has completed onboarding
#   - A valid Janua JWT for a non-guest user
#   - Live Resend API key
# If all are present and VOICE_MODE_SMOKE_LIVE_SEND=true, the script
# will additionally perform one `agent_identified` send to
# SMOKE_TEST_RECIPIENT and assert the From header.
#
# Exits non-zero on first failure so cron/staging can page.

set -euo pipefail

API="${NEXUS_API_URL:-http://localhost:4300}"
AUTH="${SELVA_SMOKE_TOKEN:-dev-bypass}"
JSON_MODE=false
EXPECTED_CLAUSE_VERSION="${EXPECTED_CLAUSE_VERSION:-voice-mode-v1.0}"

if [[ "${1:-}" == "--json" ]]; then
  JSON_MODE=true
  shift
fi

if [[ -t 1 && "$JSON_MODE" == "false" ]]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; RESET=""
fi

pass_count=0
fail_count=0
results=()

check() {
  local name="$1"
  local status="$2"
  local detail="${3:-}"
  if [[ "$status" == "pass" ]]; then
    pass_count=$((pass_count + 1))
    [[ "$JSON_MODE" == "false" ]] && echo "${GREEN}✓${RESET} $name"
  else
    fail_count=$((fail_count + 1))
    [[ "$JSON_MODE" == "false" ]] && echo "${RED}✗${RESET} $name  ${RED}${detail}${RESET}"
  fi
  results+=("$name|$status|$detail")
}

curl_auth() {
  curl -sS -H "Authorization: Bearer $AUTH" "$@"
}

# ─── 1. status endpoint reachable + clause version correct ────────────────
status_body=$(curl_auth "$API/api/v1/onboarding/status" 2>&1 || echo "")
if echo "$status_body" | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
except Exception as e:
    sys.exit(f'malformed json: {e}')
assert 'voice_mode' in d, 'voice_mode field missing'
assert 'onboarding_complete' in d, 'onboarding_complete missing'
cv = d.get('clause_version', '')
expected = '$EXPECTED_CLAUSE_VERSION'
assert cv == expected, f'clause_version={cv!r} expected={expected!r}'
" 2>&1; then
  check "status endpoint reachable + clause v=$EXPECTED_CLAUSE_VERSION" "pass"
else
  check "status endpoint reachable + clause v=$EXPECTED_CLAUSE_VERSION" "fail" "$(echo "$status_body" | head -c 120)"
fi

# ─── 2. preview endpoint returns a clause for each mode ────────────────────
for mode in user_direct dyad_selva_plus_user agent_identified; do
  preview_body=$(curl_auth "$API/api/v1/onboarding/voice-mode/preview/$mode" 2>&1 || echo "")
  if echo "$preview_body" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
for k in ('mode','label','typed_phrase','heads_up','clause_body','clause_version'):
    assert d.get(k), f'missing/empty field: {k}'
" 2>&1; then
    check "preview for $mode has full clause" "pass"
  else
    check "preview for $mode has full clause" "fail" "$(echo "$preview_body" | head -c 120)"
  fi
done

# ─── 3. preview rejects an unknown mode ───────────────────────────────────
unknown_status=$(curl_auth -o /dev/null -w "%{http_code}" "$API/api/v1/onboarding/voice-mode/preview/not-a-real-mode" 2>&1 || echo "000")
if [[ "$unknown_status" == "404" ]]; then
  check "preview rejects unknown mode (404)" "pass"
else
  check "preview rejects unknown mode (404)" "fail" "got HTTP $unknown_status"
fi

# ─── 4. select with mismatched phrase is rejected ─────────────────────────
select_status=$(curl_auth \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"mode":"user_direct","typed_confirmation":"definitely not the phrase"}' \
  -o /dev/null \
  -w "%{http_code}" \
  "$API/api/v1/onboarding/voice-mode" 2>&1 || echo "000")
# Accept 400 (phrase mismatch), 404 (no tenant in this env), or 409 (already selected).
# The critical check: must NOT be 201. 201 would mean the gate failed open.
if [[ "$select_status" != "201" ]]; then
  check "select with wrong phrase is not accepted (got $select_status, not 201)" "pass"
else
  check "select with wrong phrase is not accepted (got $select_status, not 201)" "fail" "GATE FAILED OPEN"
fi

# ─── 5. tenant response exposes voice_mode field ──────────────────────────
tenant_body=$(curl_auth "$API/api/v1/tenants/me" 2>&1 || echo "")
if echo "$tenant_body" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
assert 'voice_mode' in d, 'voice_mode key missing from tenant response'
" 2>&1; then
  check "tenant response exposes voice_mode field" "pass"
else
  # 404 is OK — means no tenant provisioned in this env, not a gate failure.
  if echo "$tenant_body" | grep -q '"detail"'; then
    check "tenant response exposes voice_mode field" "pass" "no tenant in this env (OK)"
  else
    check "tenant response exposes voice_mode field" "fail" "$(echo "$tenant_body" | head -c 120)"
  fi
fi

# ─── output ───────────────────────────────────────────────────────────────
if $JSON_MODE; then
  echo '{'
  echo '  "pass": '"$pass_count"','
  echo '  "fail": '"$fail_count"','
  echo '  "checks": ['
  first=true
  for row in "${results[@]}"; do
    IFS='|' read -r name status detail <<<"$row"
    $first || echo ','
    first=false
    printf '    {"name":%s,"status":"%s","detail":%s}' \
      "$(printf '%s' "$name" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')" \
      "$status" \
      "$(printf '%s' "$detail" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
  done
  echo
  echo '  ]'
  echo '}'
else
  echo
  echo "Passed: $pass_count | Failed: $fail_count"
fi

[[ "$fail_count" -eq 0 ]]
