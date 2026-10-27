#!/usr/bin/env bash
# fix-colour-ppd.sh - repoint stale 192.168.0.243 URLs in the Pi's colour.ppd and restart CUPS.
# Task: https://familia.riera.co.uk/tasks/3708 (superseded if the Pi is retired, see 3715/3716).
#
# Usage (ON THE PI):  fix-colour-ppd.sh            dry run: shows the lines and the diff, changes nothing
#                     fix-colour-ppd.sh --apply    backup, edit, verify, restart CUPS (needs sudo)
# Env: PPD (/etc/cups/ppd/colour.ppd)  NEW_HOST (colour.lab.riera.co.uk)  OLD_HOST (192.168.0.243)
# Safety: refuses to restart CUPS while jobs are pending; keeps a timestamped backup of the PPD;
# touches only colour.ppd. Rollback: copy the .bak-* file back, then systemctl restart cups.
set -euo pipefail
PPD=${PPD:-/etc/cups/ppd/colour.ppd}
OLD_HOST=${OLD_HOST:-192.168.0.243}
NEW_HOST=${NEW_HOST:-colour.lab.riera.co.uk}
mode=${1:-dry}

echo "== lines mentioning $OLD_HOST in $PPD"
if ! grep -n "$OLD_HOST" "$PPD"; then echo "none: nothing to do"; exit 0; fi
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
sed "s#//$OLD_HOST/#//$NEW_HOST/#g" "$PPD" > "$tmp"
echo "== diff"
diff "$PPD" "$tmp" || true
if [[ $mode != --apply ]]; then echo "dry run: re-run with --apply (sudo) to change"; exit 0; fi

[[ $EUID -eq 0 ]] || { echo "run with sudo for --apply" >&2; exit 1; }
pending=$(lpstat -o 2>/dev/null | wc -l)
[[ $pending -eq 0 ]] || { echo "ABORT: $pending job(s) pending; wait and retry" >&2; exit 1; }
curl -fsS -o /dev/null --max-time 10 "http://$NEW_HOST/" || { echo "ABORT: $NEW_HOST web UI unreachable" >&2; exit 1; }
stamp=$(date +%F-%H%M)
cp -p "$PPD" "$PPD.bak-$stamp"
install -m 644 -o root -g lp "$tmp" "$PPD"
if grep -q "$OLD_HOST" "$PPD"; then echo "FAIL: old host still present" >&2; exit 1; fi
systemctl restart cups
sleep 3
systemctl is-active cups
lpstat -p colour
echo "OK. Bonjour check from the Mac: dns-sd -B _ipp._tcp  (old '(office)' names should be gone)"
