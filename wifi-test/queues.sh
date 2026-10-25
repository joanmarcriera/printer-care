#!/usr/bin/env bash
# queues.sh - define the PARALLEL Wi-Fi test queues (black-wifi, colour-wifi) on the print Pi.
# Task: https://familia.riera.co.uk/tasks/3713 (supersedes https://familia.riera.co.uk/tasks/3708)
#
# Usage:  queues.sh                 print the lpadmin commands (default, changes nothing)
#         queues.sh --apply         run them (on the Pi, as a user allowed to lpadmin)
#         queues.sh --remove        remove ONLY the two *-wifi queues (rollback)
# Env:    BLACK_HOST (black.lab.riera.co.uk)  COLOUR_HOST (colour.lab.riera.co.uk)
#
# Safety: only ever names black-wifi / colour-wifi; the existing queues black, colour and
# colour-photo are never touched.
# Findings behind the choices (probed from the Mac 2026-10-25, read-only):
#   colour.lab: TCP 631 open, IPP get-printer-attributes PASS, formats urf/pwg-raster/jpeg
#               (no PostScript/PDF: CUPS filters do the conversion, so use a CUPS queue).
#   black.lab : IPP get-printer-attributes PASS (urf/pwg-raster; HL-L2350DW series) once awake, but
#               tcp/631 refused on the first probe while it slept => driverless is the primary
#               choice, brlaser + socket://:9100 the fallback (BLACK_MODE=brlaser).
set -euo pipefail
BLACK_HOST=${BLACK_HOST:-black.lab.riera.co.uk}
COLOUR_HOST=${COLOUR_HOST:-colour.lab.riera.co.uk}
mode=${1:-print}
BLACK_MODE=${BLACK_MODE:-driverless}   # driverless | brlaser

if [[ $BLACK_MODE == brlaser ]]; then
  black_cmd="lpadmin -p black-wifi -E -v socket://$BLACK_HOST:9100 -m drv:///brlaser.drv/brl2350dw.ppd -D 'Mono over Wi-Fi (test)' -L 'Wi-Fi test queue'"
else
  black_cmd="lpadmin -p black-wifi -E -v ipp://$BLACK_HOST/ipp/print -m everywhere -D 'Mono over Wi-Fi (test)' -L 'Wi-Fi test queue'"
fi
cmds=(
  # colour: driverless (-m everywhere), hostname URI so the stale .243 address cannot recur.
  "lpadmin -p colour-wifi -E -v ipp://$COLOUR_HOST/ipp/print -m everywhere -D 'Colour over Wi-Fi (test)' -L 'Wi-Fi test queue'"
  # black: driverless by default; BLACK_MODE=brlaser for the fallback (confirm the driver name with
  # `lpinfo -m | grep -i 'HL-L2350'` first).
  "$black_cmd"
  "lpadmin -p black-wifi -o sides-default=two-sided-long-edge"
)

case $mode in
  print|--print) printf '%s\n' "${cmds[@]}"; echo "# rollback: $0 --remove" ;;
  --apply)
    for c in "${cmds[@]}"; do echo "+ $c"; eval "$c"; done
    lpstat -p black-wifi colour-wifi ;;
  --remove)
    for q in black-wifi colour-wifi; do echo "+ lpadmin -x $q"; lpadmin -x "$q"; done ;;
  *) echo "usage: $0 [--apply|--remove]" >&2; exit 2 ;;
esac
