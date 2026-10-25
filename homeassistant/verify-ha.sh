#!/usr/bin/env bash
# verify-ha.sh - read-only check of the Home Assistant side (task https://familia.riera.co.uk/tasks/3704).
# Usage:  HA_URL=http://homeassistant.lan:8123 HA_TOKEN=<long-lived token> verify-ha.sh [--fire]
#   default : GET /api/states; PASS if >=5 brother supply sensors have a numeric state and both
#             automations (printers_supplies_low, printers_printer_care_events) exist.
#   --fire  : ALSO POST one test event to the webhook (sends a real phone notification; only on request).
#             Needs HA_WEBHOOK_ID (default printer_care).
# Exit: 0 all PASS, 1 any FAIL, 2 usage/config. The token is never printed.
set -uo pipefail
: "${HA_URL:?set HA_URL}" "${HA_TOKEN:?set HA_TOKEN}"
fails=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; fails=$((fails+1)); }
states=$(curl -fsS -m 15 -H "Authorization: Bearer $HA_TOKEN" "${HA_URL%/}/api/states") || { echo "FAIL  cannot read /api/states"; exit 1; }

n=$(printf '%s' "$states" | python3 -c '
import sys, json
s = json.load(sys.stdin)
ok = [e for e in s if e["entity_id"].startswith("sensor.") and any(k in e["entity_id"] for k in ("_ink", "_toner", "drum"))
      and e["state"].replace(".", "", 1).isdigit()]
print(len(ok))')
if [[ ${n:-0} -ge 5 ]]; then pass "$n numeric ink/toner/drum sensors"; else fail "only ${n:-0} numeric supply sensors (want >=5)"; fi

for a in printers_supplies_low printers_printer_care_events; do
  if printf '%s' "$states" | python3 -c '
import sys, json
a = sys.argv[1]
sys.exit(0 if any(e["entity_id"].startswith("automation.") and e["attributes"].get("id") == a for e in json.load(sys.stdin)) else 1)' "$a"; then
    pass "automation $a present"
  else fail "automation $a missing"; fi
done

if [[ ${1:-} == --fire ]]; then
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
    -d '{"event":"test","printer":"verify-ha","message":"verify-ha.sh test event"}' \
    "${HA_URL%/}/api/webhook/${HA_WEBHOOK_ID:-printer_care}")
  if [[ $code == 200 ]]; then pass "webhook POST -> 200 (confirm the phone notification)"; else fail "webhook POST -> $code"; fi
fi
echo "--- $fails failure(s)"
[[ $fails -eq 0 ]]
