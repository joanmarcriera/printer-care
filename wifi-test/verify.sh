#!/usr/bin/env bash
# verify.sh - checks for the Wi-Fi test queues (task https://familia.riera.co.uk/tasks/3713).
# Usage:  verify.sh net      any host, read-only: DNS + ports + IPP capabilities of both printers
#         verify.sh queues   on the Pi, read-only: *-wifi queues exist with the right URI,
#                            the three USB queues are unchanged
#         verify.sh print    on the Pi: ONE tiny text page to each *-wifi queue (a little toner/ink)
# Exit:   0 all checks passed, 1 at least one FAIL, 2 usage. One PASS/FAIL line per check.
set -uo pipefail
BLACK_HOST=${BLACK_HOST:-black.lab.riera.co.uk}
COLOUR_HOST=${COLOUR_HOST:-colour.lab.riera.co.uk}
fails=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; fails=$((fails+1)); }
# Printers sleep and the first probe often times out: try up to 3 times, 4 s apart.
port() { local _; for _ in 1 2 3; do nc -z -w 3 "$1" "$2" >/dev/null 2>&1 && return 0; sleep 4; done; return 1; }
ipp_ok() { local _ o; for _ in 1 2 3; do o=$(ipptool -T 8 -tv "ipp://$1/ipp/print" get-printer-attributes.test 2>&1); [[ $o == *"[PASS]"* ]] && return 0; sleep 4; done; return 1; }

net() {
  local h ip
  for h in "$BLACK_HOST" "$COLOUR_HOST"; do
    ip=$(dig +short "$h" | head -1)
    if [[ -n $ip ]]; then pass "dns $h -> $ip"; else fail "dns $h does not resolve"; fi
  done
  if port "$COLOUR_HOST" 631; then pass "colour tcp/631 (IPP) open"; else fail "colour tcp/631 closed"; fi
  if ipp_ok "$COLOUR_HOST"; then pass "colour IPP get-printer-attributes"; else fail "colour IPP get-printer-attributes"; fi
  if ipp_ok "$BLACK_HOST"; then pass "black IPP get-printer-attributes (driverless possible)"
  else fail "black IPP not answering: fall back to brlaser + socket://:9100"; fi
  if port "$BLACK_HOST" 9100; then pass "black tcp/9100 (raw fallback) open"; else fail "black tcp/9100 closed"; fi
}

queues() {
  local q uri
  for q in black-wifi colour-wifi colour-photo black colour; do
    if lpstat -p "$q" >/dev/null 2>&1; then pass "queue $q exists"; else fail "queue $q missing"; fi
  done
  uri=$(lpstat -v colour-wifi 2>/dev/null)
  if [[ $uri == *"ipp://$COLOUR_HOST/ipp/print"* ]]; then pass "colour-wifi URI by hostname"; else fail "colour-wifi URI: ${uri:-none}"; fi
  uri=$(lpstat -v black-wifi 2>/dev/null)
  if [[ $uri == *"$BLACK_HOST"* ]]; then pass "black-wifi URI by hostname"; else fail "black-wifi URI: ${uri:-none}"; fi
  for q in black colour colour-photo; do
    uri=$(lpstat -v "$q" 2>/dev/null)
    if [[ $uri == *usb:* || $uri == *localhost:60000* ]]; then pass "existing $q still USB/ipp-usb"
    else fail "existing $q changed: ${uri:-none}"; fi
  done
}

print_pages() {
  local q out id
  for q in black-wifi colour-wifi; do
    out=$(echo "printer-care wifi test $q $(date +%F)" | lp -d "$q" -t "wifi-test-$q" 2>&1)
    id=$(echo "$out" | grep -o "$q-[0-9]*" | head -1)
    if [[ -z $id ]]; then fail "$q: lp gave no job id ($out)"; continue; fi
    for _ in $(seq 1 24); do lpstat -o "$q" 2>/dev/null | grep -q "^$id " || break; sleep 5; done
    if lpstat -o "$q" 2>/dev/null | grep -q "^$id "; then fail "$q: $id still queued after 2 min"
    else pass "$q: $id left the queue (confirm the paper)"; fi
  done
}

case ${1:-} in
  net) net ;;
  queues) queues ;;
  print) print_pages ;;
  *) echo "usage: $0 net|queues|print" >&2; exit 2 ;;
esac
echo "--- $fails failure(s)"
[[ $fails -eq 0 ]]
