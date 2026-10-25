# Phase F4: test printing over Wi-Fi (parallel queues)

Task <https://familia.riera.co.uk/tasks/3713>. Supersedes <https://familia.riera.co.uk/tasks/3708> if we migrate.
The existing queues `black`, `colour` and `colour-photo` stay on USB, untouched. Two **new** queues sit beside them.

## Prepared in this repo (nothing applied anywhere)

| File | Purpose |
|---|---|
| `wifi-test/queues.sh` | Prints (default), applies (`--apply`) or removes (`--remove`) `black-wifi` and `colour-wifi`. Only ever names those two. |
| `wifi-test/verify.sh net\|queues\|print` | `net`: DNS, ports, IPP from any host. `queues`: on the Pi, checks the new queues and that the USB ones are unchanged. `print`: one tiny page per new queue. Exit 0 = all PASS. |

Facts probed read-only from the Mac on 2026-10-25 (re-run `verify.sh net` to refresh):

- `colour.lab.riera.co.uk` = 192.168.0.11, tcp/631 open, IPP PASS, DCP-T780DW. Formats: urf, pwg-raster, jpeg (**no PostScript or PDF**),
  so a CUPS queue (`-m everywhere`) is needed to convert; the keep-alive page is PostScript.
- `black.lab.riera.co.uk` = 192.168.0.10, HL-L2350DW series, IPP PASS (urf, pwg-raster), tcp/9100 open. The first probe found
  tcp/631 refused while the printer slept, so **driverless works once awake**; brlaser + `socket://:9100` is the fallback
  (`BLACK_MODE=brlaser`). Waking from sleep is exactly what the overnight test below exercises.

## Gate: apply on the Pi (Marc)

```sh
scp wifi-test/queues.sh wifi-test/verify.sh <pi>:/tmp/ && ssh <pi> 'bash /tmp/queues.sh --apply && bash /tmp/verify.sh queues'
```
Rollback: `bash /tmp/queues.sh --remove`. Review first with `wifi-test/queues.sh` (prints the commands only).

## Test matrix (record PASS/FAIL and the paper in the task comment)

| # | Case | Queue / path | How |
|---|---|---|---|
| 1 | Mono, duplex | black-wifi | `lp -d black-wifi -o sides=two-sided-long-edge file.pdf` |
| 2 | Colour | colour-wifi | `lp -d colour-wifi file.pdf` |
| 3 | Glossy photo | colour-wifi | photo on glossy stock, media `na_letter`/`iso_a4` + `media-type=photographic-glossy`; compare with `colour-photo` on USB |
| 4 | After overnight sleep | both | no traffic overnight, first job next morning: must print without manual wake; note delay |
| 5 | Mac | both | System Settings > Printers, or `lp -d` |
| 6 | iPhone | direct AirPrint to the printer | no Pi |
| 7 | Android | direct (Default Print Service / Brother app) | no Pi |
| 8 | Windows | IPP printer (`ipp://colour.lab.riera.co.uk/ipp/print`, driverless) | no Pi |
| 9 | Direct AirPrint, no Pi | printers' own AirPrint | this is the end state; if 6-8 pass for a printer, the Pi is not needed for it |

Pass bar per case: job prints correctly, queue empty afterwards (`lpstat -o` empty), no entry in `/var/log/cups/error_log`.
Counters: `printer-care status` colour counter should rise by the pages printed in cases 2-3 (it reads the printer, not the path).

## Notes

- Hostname URIs (never IPs) retire the stale `.243` problem of <https://familia.riera.co.uk/tasks/3708>.
- Direct printing bypasses CUPS, so `page_log` will not see those jobs (see `docs/pi-job-options.md`, job 2).
- Decision input for <https://familia.riera.co.uk/tasks/3714> and <https://familia.riera.co.uk/tasks/3715>.
