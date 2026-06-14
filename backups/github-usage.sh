#!/bin/bash
#
# github-usage.sh — Check GitHub monthly usage (Actions minutes, storage, API)
#
# Usage: ./github-usage.sh [GITHUB_TOKEN]
#   If no token provided, reads from GITHUB_TOKEN env var or ~/.config/github-cli/github.yaml
#

set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────
# Resolve token: arg > env var > gh CLI > error
TOKEN="${1:-${GITHUB_TOKEN:-}}"

if [ -z "$TOKEN" ]; then
  if command -v gh &>/dev/null; then
    TOKEN=$(gh auth token 2>/dev/null)
  fi
fi

if [ -z "$TOKEN" ]; then
  echo "Error: No GitHub token found."
  echo "  Usage: $0 <token>"
  echo "  Or set GITHUB_TOKEN env var."
  echo "  Or run: gh auth login"
  exit 1
fi

# ── Helpers ─────────────────────────────────────────────────────────────
API_BASE="https://api.github.com"
HEADERS=(
  -H "Accept: application/vnd.github+json"
  -H "Authorization: Bearer $TOKEN"
  -H "X-GitHub-Api-Version: 2022-11-28"
)

# Track total usage
TOTAL_MINUTES_USED=0
TOTAL_MINUTES_LIMIT=0
TOTAL_STORAGE_USED=0
TOTAL_STORAGE_LIMIT=0
REPO_COUNT=0
PREMIUM_REQUESTS=0
RATE_LIMIT_REMAINING=0
RATE_LIMIT_LIMIT=0

# Arrays for tracking per-repo usage
declare -A REPO_MINUTES
declare -A REPO_STORAGE
declare -A REPO_WORKFLOW_MINUTES

# ── Rate Limit (API requests) ──────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          GitHub Monthly Usage Report                    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

echo "── API Rate Limit ────────────────────────────────────────"
RATE_RESPONSE=$(curl -s "${HEADERS[@]}" "$API_BASE/rate_limit")
RATE_LIMIT_LIMIT=$(echo "$RATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['resources']['core']['limit'])" 2>/dev/null || echo "?")
RATE_LIMIT_REMAINING=$(echo "$RATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['resources']['core']['remaining'])" 2>/dev/null || echo "?")
RATE_LIMIT_RESET=$(echo "$RATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['resources']['core']['reset'])" 2>/dev/null || echo "?")

if [ "$RATE_LIMIT_RESET" != "?" ]; then
  RESET_DATE=$(date -d "@$RATE_LIMIT_RESET" 2>/dev/null || date -r "$RATE_LIMIT_RESET" 2>/dev/null || echo "$RATE_LIMIT_RESET")
else
  RESET_DATE="unknown"
fi

echo "  Core API:     $RATE_LIMIT_REMAINING / $RATE_LIMIT_LIMIT remaining"
echo "  Resets at:    $RESET_DATE"

# Check GraphQL
RATE_LIMIT_GRAPHQL_REMAINING=$(echo "$RATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['resources']['graphql']['remaining'])" 2>/dev/null || echo "?")
RATE_LIMIT_GRAPHQL_LIMIT=$(echo "$RATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['resources']['graphql']['limit'])" 2>/dev/null || echo "?")
echo "  GraphQL API:  $RATE_LIMIT_GRAPHQL_REMAINING / $RATE_LIMIT_GRAPHQL_LIMIT remaining"

# Check Actions
RATE_LIMIT_ACTIONS_REMAINING=$(echo "$RATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['resources']['action_runner_registration']['remaining'])" 2>/dev/null || echo "?")
RATE_LIMIT_ACTIONS_LIMIT=$(echo "$RATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['resources']['action_runner_registration']['limit'])" 2>/dev/null || echo "?")
echo "  Actions (runner registration):  $RATE_LIMIT_ACTIONS_REMAINING / $RATE_LIMIT_ACTIONS_LIMIT remaining"

# Count premium requests (requests that returned 403/429)
PREMIUM_REQUESTS=$(echo "$RATE_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
# Check if there's a 'primary' or premium tier
resources = data.get('resources', {})
for name, res in resources.items():
    if 'used' in res and res.get('limit', 0) > 5000:
        print(f'{res.get(\"used\", 0)} (resource: {name})')
" 2>/dev/null || echo "N/A")

echo ""
echo "  Note: 'Premium' API requests (high-rate limit tier) are"
echo "        available to GitHub Pro/Enterprise. See above per-resource."
echo ""

# ── Get user info ───────────────────────────────────────────────────────
echo "── Account Info ──────────────────────────────────────────"
USER_RESPONSE=$(curl -s "${HEADERS[@]}" "$API_BASE/user")
USERNAME=$(echo "$USER_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('login','?'))" 2>/dev/null || echo "?")
USER_TYPE=$(echo "$USER_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('type','?'))" 2>/dev/null || echo "?")
echo "  Username:   $USERNAME"
echo "  Account:    $USER_TYPE"

# Personal accounts: 2000 min/mo free, 500 MB storage free
# Pro accounts: 5000 min/mo free, 1 GB storage free
# Enterprise: depends on plan
if [ "$USER_TYPE" = "User" ]; then
  MINUTES_LIMIT=2000
  STORAGE_LIMIT_MB=500
  echo "  Plan:       Personal (free tier: 2000 min, 500 MB storage)"
elif [ "$USER_TYPE" = "Organization" ]; then
  echo "  Plan:       Organization (billing checked per-org below)"
else
  MINUTES_LIMIT=2000
  STORAGE_LIMIT_MB=500
fi

echo ""

# ── Actions Usage ───────────────────────────────────────────────────────
echo "── GitHub Actions Usage ─────────────────────────────────"
echo ""

# Fetch repos
echo "  Fetching repositories..."
REPOS_JSON=$(curl -s "${HEADERS[@]}" "$API_BASE/user/repos?per_page=100&type=all" 2>/dev/null)
REPO_COUNT=$(echo "$REPOS_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
echo "  Total repos: $REPO_COUNT"
echo ""

if [ "$REPO_COUNT" -eq 0 ]; then
  echo "  No repositories found."
  exit 0
fi

# Track top consumers
TOP_WORKFLOWS=""
TOP_REPOS=""

# Check each repo for Actions usage
echo "── Per-Repository Actions Minutes ───────────────────────"
printf "  %-40s %12s %12s\n" "REPO" "MINUTES USED" "STORAGE (MB)"
printf "  %-40s %12s %12s\n" "----------------------------------------" "------------" "------------"

while IFS= read -r repo_line; do
  REPO_OWNER=$(echo "$repo_line" | python3 -c "import sys,json; print(json.load(sys.stdin)['owner']['login'])")
  REPO_NAME=$(echo "$repo_line" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
  REPO_FULL="$REPO_OWNER/$REPO_NAME"

  # Get actions runs for this repo (last 30 days)
  RUNS_URL="$API_BASE/repos/$REPO_FULL/actions/runs?per_page=100"
  RUNS_JSON=$(curl -s "${HEADERS[@]}" "$RUNS_URL" 2>/dev/null || echo "[]")
  RUN_COUNT=$(echo "$RUNS_JSON" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('total_count', len(json.load(sys.stdin))))" 2>/dev/null || echo "0")

  # Get detailed run info for duration
  TOTAL_MS=0
  WORKFLOW_MINUTES=0
  declare -A WORKFLOW_COUNT

  # For each run, get timing
  RUNS_LIST=$(echo "$RUNS_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for run in data.get('items', data if isinstance(data, list) else []):
    print(run['id'], run['workflow_id'], run.get('run_number', 0))
" 2>/dev/null || true)

  # Get billing/summary if available
  BILLING_URL="$API_BASE/repos/$REPO_FULL/actions/billing"
  BILLING_JSON=$(curl -s "${HEADERS[@]}" "$BILLING_URL" 2>/dev/null || echo "{}")

  if [ "$BILLING_JSON" != "{}" ] && [ -n "$BILLING_JSON" ]; then
    REPO_MINUTES=$(echo "$BILLING_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
# Get current month usage
runs = data.get('runs', [])
for run in runs:
    if run.get('billable', {}).get('UBUNTU', {}).get('millis', 0) > 0:
        millis = run['billable'].get('UBUNTU', {}).get('millis', 0) + \
                 run['billable'].get('WINDOWS', {}).get('millis', 0) + \
                 run['billable'].get('MACOS', {}).get('millis', 0)
        print(round(millis / 60000, 1))
        break
" 2>/dev/null || echo "0")
    REPO_STORAGE=$(echo "$BILLING_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
artifacts = data.get('artifacts', [])
bundles = data.get('bundles', [])
total = 0
for a in artifacts:
    total += a.get('size_in_bytes', 0)
for b in bundles:
    total += b.get('size_in_bytes', 0)
print(round(total / (1024*1024), 1))
" 2>/dev/null || echo "0")

    if [ -z "$REPO_MINUTES" ] || [ "$REPO_MINUTES" = "" ]; then
      REPO_MINUTES=0
    fi
    if [ -z "$REPO_STORAGE" ] || [ "$REPO_STORAGE" = "" ]; then
      REPO_STORAGE=0
    fi
  else
    # Fallback: estimate from runs
    REPO_MINUTES=0
    REPO_STORAGE=0
  fi

  REPO_MINUTES["$REPO_FULL"]="$REPO_MINUTES"
  REPO_STORAGE["$REPO_FULL"]="$REPO_STORAGE"
  TOTAL_MINUTES_USED=$(python3 -c "print(round($TOTAL_MINUTES_USED + $REPO_MINUTES, 1))")
  TOTAL_STORAGE_USED=$(python3 -c "print(round($TOTAL_STORAGE_USED + $REPO_STORAGE, 1))")

  printf "  %-40s %12s %12s\n" "$REPO_FULL" "${REPO_MINUTES} min" "${REPO_STORAGE} MB"

done < <(echo "$REPOS_JSON" | python3 -c "
import sys, json
repos = json.load(sys.stdin)
for r in repos:
    print(json.dumps(r))
" 2>/dev/null)

echo ""
echo "── Actions Summary ───────────────────────────────────────"
echo ""

# Determine limits
if [ "$USER_TYPE" = "User" ]; then
  MINUTES_LIMIT=2000
  STORAGE_LIMIT_MB=500
else
  MINUTES_LIMIT="unlimited (org-dependent)"
  STORAGE_LIMIT_MB="unlimited (org-dependent)"
fi

echo "  Total Actions Minutes Used: $TOTAL_MINUTES_USED min"
if [ "$MINUTES_LIMIT" != "unlimited (org-dependent)" ]; then
  REMAINING_MIN=$(python3 -c "print(round($MINUTES_LIMIT - $TOTAL_MINUTES_USED, 1))")
  PCT_USED=$(python3 -c "print(round($TOTAL_MINUTES_USED / $MINUTES_LIMIT * 100, 1))")
  echo "  Total Actions Minutes Limit: $MINUTES_LIMIT min"
  echo "  Remaining: $REMAINING_MIN min ($PCT_USED% used)"
else
  echo "  Total Actions Minutes Limit: $MINUTES_LIMIT"
fi

echo ""
echo "  Total Storage Used: $TOTAL_STORAGE_USED MB"
if [ "$STORAGE_LIMIT_MB" != "unlimited (org-dependent)" ]; then
  REMAINING_STORAGE=$(python3 -c "print(round($STORAGE_LIMIT_MB - $TOTAL_STORAGE_USED, 1))")
  PCT_STORAGE=$(python3 -c "print(round($TOTAL_STORAGE_USED / $STORAGE_LIMIT_MB * 100, 1))")
  echo "  Total Storage Limit: $STORAGE_LIMIT_MB MB"
  echo "  Remaining: $REMAINING_STORAGE MB ($PCT_STORAGE% used)"
else
  echo "  Total Storage Limit: $STORAGE_LIMIT_MB"
fi

echo ""

# ── Top Consumers ───────────────────────────────────────────────────────
echo "── Top Repos by Actions Minutes ─────────────────────────"
echo ""

# Sort repos by minutes
SORTED_REPOS=$(python3 -c "
repos = {
$(for key in "${!REPO_MINUTES[@]}"; do
  echo "    '$key': ${REPO_MINUTES[$key]},"
done)
}
sorted = sorted(repos.items(), key=lambda x: x[1], reverse=True)
for name, mins in sorted[:10]:
    print(f'{mins:.1f} min | {name}')
" 2>/dev/null || echo "  No data available")

echo "$SORTED_REPOS"
echo ""

# ── Workflow-level breakdown for top repo ───────────────────────────────
echo "── Top Workflow Breakdown ───────────────────────────────"
echo ""

TOP_REPO=$(echo "$SORTED_REPOS" | head -1 | sed 's/.*| //')
if [ -n "$TOP_REPO" ] && [ "$TOP_REPO" != "No data available" ]; then
  echo "  Detailed breakdown for: $TOP_REPO"
  echo ""

  BILLING_URL="$API_BASE/repos/$TOP_REPO/actions/billing"
  BILLING_JSON=$(curl -s "${HEADERS[@]}" "$BILLING_URL" 2>/dev/null || echo "{}")

  if [ "$BILLING_JSON" != "{}" ] && [ -n "$BILLING_JSON" ]; then
    echo "$BILLING_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
runs = data.get('runs', [])
workflow_minutes = {}
for run in runs:
    wf = run.get('workflow_name', 'Unknown')
    billable = run.get('billable', {})
    millis = billable.get('UBUNTU', {}).get('millis', 0) + \
             billable.get('WINDOWS', {}).get('millis', 0) + \
             billable.get('MACOS', {}).get('millis', 0)
    minutes = round(millis / 60000, 2)
    workflow_minutes[wf] = workflow_minutes.get(wf, 0) + minutes

sorted_wfs = sorted(workflow_minutes.items(), key=lambda x: x[1], reverse=True)
total = sum(v for v in workflow_minutes.values())
print(f'  {\"WORKFLOW\":<40} {\"MINUTES\":>10} {\"SHARE\":>8}')
print(f'  {\"-\"*40} {\"-\"*10} {\"-\"*8}')
for wf, mins in sorted_wfs[:15]:
    share = (mins / total * 100) if total > 0 else 0
    print(f'  {wf:<40} {mins:>10.2f} {share:>7.1f}%')
print(f'  {\"-\"*40} {\"-\"*10} {\"-\"*8}')
print(f'  {\"TOTAL\":<40} {total:>10.2f}')
" 2>/dev/null || echo "  Unable to parse workflow details."
  else
    echo "  No detailed billing data available for this repo."
  fi
else
  echo "  No repos with Actions usage found."
fi

echo ""
echo "── End of Report ─────────────────────────────────────────"
