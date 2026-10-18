#!/usr/bin/env bash
# Test runner for printer-care - pure bash, no bats. Sources the script and checks
# the pure functions plus a few `check` scenarios against fixtures in a temp dir.
# Usage: tests/run.sh        (exit 0 = all passed)
# Never touches CUPS, the network or real state: PRINTER_CARE_* env points at fixtures.
# shellcheck disable=SC1091,SC2015,SC2016,SC2030,SC2031,SC2034  # test idioms: A && B || C, subshell env, vars used by the sourced script
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
FX=$HERE/fixtures
# shellcheck source=../printer-care
source "$HERE/../printer-care"
set +e   # the script sets -e; the runner wants to keep going after a failed check

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
NOW=1792324800   # 2026-10-18 12:00 UTC
PASS=0 FAIL=0

ok()   { PASS=$((PASS+1)); }
bad()  { FAIL=$((FAIL+1)); printf 'FAIL: %s\n  expected: %s\n  actual:   %s\n' "$1" "$2" "$3"; }
eq()   { [[ "$3" == "$2" ]] && ok || bad "$1" "$2" "$3"; }          # eq NAME EXPECTED ACTUAL
has()  { [[ "$3" == *"$2"* ]] && ok || bad "$1" "contains '$2'" "$3"; }
hasnt(){ [[ "$3" != *"$2"* ]] && ok || bad "$1" "does not contain '$2'" "$3"; }

# --- TLV decoding (counters fixture is wrapped over 3 lines, like real snmpget output)
HEX=$(norm_hex "$(cat "$FX/counters.snmp")")
eq "tlv total"  5 "$(decode_tlv "$HEX" 00)"
eq "tlv colour" 3 "$(decode_tlv "$HEX" 02)"
eq "tlv mono"   2 "$(decode_tlv "$HEX" 01)"
eq "tlv duplex" 0 "$(decode_tlv "$HEX" 06)"
decode_tlv "$HEX" 55 >/dev/null; eq "tlv missing code -> rc 1" 1 $?
eq "tlv mono printer total" 7592 "$(decode_tlv "$(cat "$FX/mono-counters.hex")" 00)"
eq "tlv 4-byte value" 3231 "$(decode_tlv "$(cat "$FX/mono-counters.hex")" 06)"
MAINT=$(norm_hex "$(cat "$FX/maint.snmp")")
eq "maint 0x81" 99 "$(decode_tlv "$MAINT" 81)"
eq "maint 0x6F" 9900 "$(decode_tlv "$MAINT" 6F)"
eq "ink_from_maint" "K=99 C=99 M=99 Y=99" "$(ink_from_maint "$MAINT")"
eq "tlv truncated blob is safe" "" "$(decode_tlv '00 01 04 00 00' 00)"
eq "pct_ceil drum" 68 "$(pct_ceil 8093 12000)"
pct_ceil 5 -2 >/dev/null; eq "pct_ceil unknown max -> rc 1" 1 $?
eq "markers_parse" "M 99
C 99
Y 99
BK 50" "$(markers_parse < "$FX/ipp.sample")"

# --- time + decision table
eq "days_between 6d" 6 "$(days_between 0 $((6*86400+100)))"
eq "days_between negative" 0 "$(days_between 1000 10)"
eq "decide 6 days -> wait"  wait  "$(decide_keepalive $((NOW)) $((NOW-6*86400)) 7 0)"
eq "decide 7 days -> print" print "$(decide_keepalive $((NOW)) $((NOW-7*86400)) 7 0)"
eq "decide due+pending -> stuck" stuck "$(decide_keepalive $((NOW)) $((NOW-9*86400)) 7 1)"
eq "decide pending not due -> wait" wait "$(decide_keepalive $((NOW)) $((NOW-1*86400)) 7 1)"
eq "decide no timestamp -> wait" wait "$(decide_keepalive "$NOW" "" 7 0)"

# --- counter clock
COLOUR_CHANGED_AT='' COLOUR_COUNT=''; apply_counter 3 "$NOW"
eq "seed clock" "$NOW/3" "$COLOUR_CHANGED_AT/$COLOUR_COUNT"
apply_counter 3 $((NOW+86400)); eq "same counter keeps clock" "$NOW" "$COLOUR_CHANGED_AT"
apply_counter 4 $((NOW+2*86400)); eq "counter rose resets clock" "$((NOW+2*86400))/4" "$COLOUR_CHANGED_AT/$COLOUR_COUNT"
apply_counter 1 $((NOW+3*86400)); eq "counter reset re-baselines only" "$((NOW+2*86400))/1" "$COLOUR_CHANGED_AT/$COLOUR_COUNT"

# --- check scenarios in an isolated state dir (subshells so globals/exit don't leak)
SD=$TMP/sd
run_check() {   # run_check STATEFILE_CONTENT FIXTURE [args...] -> stdout+stderr; state dir is $SD
  local content=$1 fix=$2; shift 2
  rm -rf "$SD"; mkdir -p "$SD"
  [[ -z $content ]] || printf '%s\n' "$content" > "$SD/state"
  (
    export PRINTER_CARE_CONF=/dev/null PRINTER_CARE_STATE_DIR=$SD PRINTER_CARE_NOW=$NOW \
           PRINTER_CARE_SNMP_FIXTURE=$fix PRINTER_CARE_USB=yes COLOUR_HOST=colour-printer.example.lan
    main check "$@"
  ) 2>&1
}
sget() { sed -n "s/^$1=//p" "$SD/state"; }

out=$(run_check "" "$FX/counters.snmp"); rc=$?
eq "first run rc" 0 "$rc"; eq "first run seeds clock" "$NOW" "$(sget COLOUR_CHANGED_AT)"; eq "first run seeds count" 3 "$(sget COLOUR_COUNT)"

out=$(run_check "COLOUR_COUNT=2
COLOUR_CHANGED_AT=$((NOW-20*86400))" "$FX/counters.snmp"); rc=$?
eq "counter rose -> clock reset" "$NOW" "$(sget COLOUR_CHANGED_AT)"; eq "counter rose -> no keepalive" 0 "$rc"
hasnt "counter rose -> nothing printed" "no colour for" "$out"

out=$(run_check "COLOUR_COUNT=3
COLOUR_CHANGED_AT=$((NOW-8*86400))" "$FX/counters.snmp" --dry-run); rc=$?
has "due + dry-run says would print" "would print keep-alive" "$out"
eq "dry-run leaves no state change" "$((NOW-8*86400))" "$(sget COLOUR_CHANGED_AT)"
eq "dry-run rc" 0 "$rc"

out=$(run_check "COLOUR_COUNT=3
COLOUR_CHANGED_AT=$((NOW-8*86400))" "$FX/counters.snmp" --dry-run); has "dry-run no webhook" "dry-run" "$out"

out=$( rm -rf "$SD"; mkdir -p "$SD"; printf 'COLOUR_COUNT=3\nCOLOUR_CHANGED_AT=%s\n' $((NOW-8*86400)) > "$SD/state"
  export PRINTER_CARE_CONF=/dev/null PRINTER_CARE_STATE_DIR=$SD PRINTER_CARE_NOW=$NOW PRINTER_CARE_SNMP_FIXTURE=$FX/counters.snmp PRINTER_CARE_USB=no
  main check --dry-run 2>&1 ); rc=$?
has "USB absent -> printer_absent" "printer_absent" "$out"; eq "USB absent rc" 3 "$rc"

out=$(run_check "COLOUR_COUNT=3
COLOUR_CHANGED_AT=$((NOW-2*86400))
LAST_KEEPALIVE_AT=$((NOW-7200))
LAST_KEEPALIVE_JOB=colour-1
COUNT_AT_KEEPALIVE=3" "$FX/counters.snmp"); rc=$?
has "keepalive not counted" "keepalive_not_counted" "$out"; eq "not counted rc" 3 "$rc"
eq "job cleared after verification" "" "$(sget LAST_KEEPALIVE_JOB)"

out=$(run_check "COLOUR_COUNT=2
COLOUR_CHANGED_AT=$((NOW-2*86400))
LAST_KEEPALIVE_AT=$((NOW-7200))
LAST_KEEPALIVE_JOB=colour-1
COUNT_AT_KEEPALIVE=2" "$FX/counters.snmp"); rc=$?
has "keepalive verified" "verified" "$out"; eq "verified rc" 0 "$rc"

# SNMP unreadable: 3 consecutive misses notify exactly on the third
printf 'garbage\n' > "$TMP/bad.snmp"
out=$(run_check "SNMP_MISSES=1
COLOUR_CHANGED_AT=$((NOW-2*86400))" "$TMP/bad.snmp"); hasnt "2nd miss silent" "counter_unreadable" "$out"; eq "misses=2" 2 "$(sget SNMP_MISSES)"
out=$(run_check "SNMP_MISSES=2
COLOUR_CHANGED_AT=$((NOW-2*86400))" "$TMP/bad.snmp"); rc=$?
has "3rd miss notifies" "counter_unreadable" "$out"; eq "3rd miss rc" 3 "$rc"
out=$(run_check "SNMP_MISSES=2
COLOUR_COUNT=3
COLOUR_CHANGED_AT=$((NOW-2*86400))" "$FX/counters.snmp"); eq "success resets misses" 0 "$(sget SNMP_MISSES)"
out=$(run_check "SNMP_MISSES=1
COLOUR_COUNT=3
COLOUR_CHANGED_AT=$((NOW-8*86400))" "$TMP/bad.snmp" --dry-run)
has "unreadable falls back to stored timestamps" "no colour for" "$out"

# --- page_log parsing
CUT=$(fmt_epoch $((NOW-30*86400)) %Y%m%d%H%M%S)
eq "page_log summary" "black 2 0 2 0 -
colour 4 3 0 1 20261018103042" "$(history_summary "$FX/page_log.sample" "$CUT")"
eq "page_log short window" "black 2 0 2 0 -
colour 2 2 0 0 20261018103042" "$(history_summary "$FX/page_log.sample" 20261018000000)"
out=$( PRINTER_CARE_CONF=/dev/null PAGE_LOG=$TMP/none PRINTER_CARE_NOW=$NOW main history 2>&1 ); has "missing page_log is graceful" "not readable" "$out"

# --- config parser: whitelist, no evaluation, env wins
cat > "$TMP/evil.conf" <<EOT
# comment
FOO=\$(touch $TMP/pwned1)
COLOUR_QUEUE=\$(touch $TMP/pwned2)
BLACK_QUEUE = "lj"
KEEPALIVE_DAYS=9
HA_WEBHOOK_URL=http://ha.example.lan:8123/api/webhook/x?y=1
\`touch $TMP/pwned3\`
LOW_INK_PERCENT=20
EOT
out=$( unset FOO COLOUR_QUEUE BLACK_QUEUE KEEPALIVE_DAYS HA_WEBHOOK_URL
  export PRINTER_CARE_CONF=$TMP/evil.conf LOW_INK_PERCENT=30
  load_config; echo "${FOO-unset}|$COLOUR_QUEUE|$BLACK_QUEUE|$KEEPALIVE_DAYS|$HA_WEBHOOK_URL|$LOW_INK_PERCENT" )
eq "config parse" "unset|\$(touch $TMP/pwned2)|lj|9|http://ha.example.lan:8123/api/webhook/x?y=1|30" "$out"
[[ ! -e $TMP/pwned1 && ! -e $TMP/pwned2 && ! -e $TMP/pwned3 ]] && ok || bad "no command executed from config" "no files" "$(ls "$TMP"/pwned* 2>&1)"
out=$( unset KEEPALIVE_DAYS; printf 'KEEPALIVE_DAYS=abc\n' > "$TMP/bad.conf"; PRINTER_CARE_CONF=$TMP/bad.conf load_config 2>&1 ); has "bad KEEPALIVE_DAYS rejected" "positive integer" "$out"

# --- state: injection + atomic write
SD=$TMP/st; mkdir -p "$SD"; printf 'COLOUR_COUNT=$(touch %s/pwned4)\nLAST_KEEPALIVE_JOB=colour-7;rm\nCOLOUR_CHANGED_AT=42\n' "$TMP" > "$SD/state"
STATE_FILE=$SD/state STATE_DIR=$SD; state_load
eq "state: non-numeric dropped" "" "$COLOUR_COUNT"; eq "state: odd job id dropped" "" "$LAST_KEEPALIVE_JOB"; eq "state: good value kept" 42 "$COLOUR_CHANGED_AT"
[[ ! -e $TMP/pwned4 ]] && ok || bad "state not executed" "no file" "exists"
COLOUR_COUNT=7; DRY=0; state_save; eq "state_save roundtrip" 7 "$(sed -n 's/^COLOUR_COUNT=//p' "$SD/state")"
eq "no temp files left" 1 "$(find "$SD" -type f | wc -l | tr -d ' ')"

# --- notification payload + PostScript
eq "json_escape quotes" 'say \"hi\" \\ x\ny' "$(json_escape $'say "hi" \\ x\ny')"
ps=$(gen_ps colour "title (x)" "line \\ two")
has "ps escapes parens" 'title \(x\)' "$ps"; has "ps has cyan bar" "0 1 1 setrgbcolor 80 740 400 6 rectfill" "$ps"; has "ps ends" "showpage" "$ps"
hasnt "mono ps has no colour" "setrgbcolor" "$(gen_ps mono t s)"

# --- CLI surface
out=$(main --help); has "help is the header" "Exit codes:" "$out"
out=$(main bogus 2>&1); rc=$?; eq "unknown command rc" 1 $rc

echo "passed: $PASS  failed: $FAIL"
[[ $FAIL -eq 0 ]]
