# What the Pi does today, and where each job could live

Input for the DECIDE task <https://familia.riera.co.uk/tasks/3714> (feeds the ADR in homelab
`docs/decisions/` and phase F5 <https://familia.riera.co.uk/tasks/3715>). **Options only: nothing here
is decided, and nothing was changed on the Pi.** Effort: S = under an hour, M = half a day, L = a day or more.
Written 2026-10-25 from the repo, not from a live look at the Pi: re-check anything marked *verify*.

Go/no-go from F2 (<https://familia.riera.co.uk/tasks/3711>) still decides, per printer, whether the Pi is
removable at all. A printer that fails the soak keeps its USB path and the jobs below stay on the Pi for it.

## Summary (recommendation first)

| Job | Recommended home | Effort |
|---|---|---|
| Colour keep-alive | printer-care unchanged, on TrueNAS, printing via a local CUPS client queue (option A2) | M |
| Page log / history | SNMP counters into HA (A), drop per-job history (accept the loss) | S |
| Queue defaults | CUPS presets on the TrueNAS queue if it has one, else client presets + the `print` skill | S |
| Sharing | Direct AirPrint/IPP from the printers; no Samba/WSD unless a Windows client needs it | S |
| Name `printer.lab.riera.co.uk` | CNAME/A to whichever host runs the surviving queue; the `print` skill points at the printers | S |

The one real piece of work is the keep-alive. The rest is deleting things.

## 1. Colour keep-alive (printer-care)

What it needs today, from the code:

- `snmpget`/`snmpwalk` to the printer (Brother private counter OID), `ipptool` for ink levels: both
  network-only, so they work from any host that can reach `colour.lab.riera.co.uk`.
- `lp -d <queue>` with a **PostScript** page on stdin (`print_ps`), then `lpstat -o` to verify the job left
  the queue. So it needs a CUPS client and a named queue, not just an IP.
- `lsusb` for the "USB device present" check and `printer_absent` event: meaningless without USB.
- State in `/var/lib/printer-care/state` (colour clock, last keep-alive). Copy it, or reseed: a first run
  seeds the clock and the worst case is one extra keep-alive page a week later.
- Optional HA webhook via `curl`.

| Option | How | Pros | Cons | Effort |
|---|---|---|---|---|
| A1. Stay on the Pi | Leave as is | Zero change | Pi stays in the estate, defeats the removal | S (0) |
| **A2. TrueNAS, keep `lp`** | systemd timer or cron on TrueNAS host (or a small Debian container) running printer-care unchanged; a local CUPS (client + `lpadmin -p colour -v ipp://colour.lab.riera.co.uk/ipp/print -m everywhere`) | Script untouched, tests still valid, verification by `lpstat` keeps working | TrueNAS 25.04 is an appliance: host installs do not survive upgrades, so it must be a container/app; needs a CUPS daemon there (or `cups-client` pointed at another server via `CUPS_SERVER`) | M |
| A3. Run it on another always-on host | optiplex990 or the Hetzner box is not on the LAN path; optiplex990 (`192.168.0.234`) is the natural one: same as A2, plain Debian | Not an appliance, normal `apt install`, `make install HOST=` works already | One more box owning a job; it is the "backup/test box" | S-M |
| A4. Rewrite to talk IPP directly | Replace `lp`/`lpstat` with `ipptool` Print-Job + Get-Job-Attributes | No CUPS anywhere | New code and tests; **the page is PostScript, which a driverless IPP printer may not accept** (*verify* `document-format-supported` via `ipptool -tv ... get-printer-attributes.test`); would need PDF or PWG-raster output instead; the 2026-10-18 note shows URF works over IPP | L |
| A5. Printer-side feature | Brother web UI / firmware periodic cleaning or "Auto Cleaning" | Nothing to run | A scheduled cleaning is not a keep-alive page, uses more ink than the CMY page, and the colour-counter verification is lost | S, not recommended |

Recommendation: **A3 if optiplex990 is staying, otherwise A2.** Both keep the script and its tests. Do A4 only
if Marc wants zero CUPS in the estate; it is the only option with real new code.
Whichever home is chosen: set `COLOUR_HOST=colour.lab.riera.co.uk` (hostname, not IP, the stale `.243`
problem of <https://familia.riera.co.uk/tasks/3708>), and decide what to do with the USB check (a `USB_CHECK=0`
style switch is a small change, S, not made here).

## 2. Page log / history (`printer-care history`)

`history` parses CUPS `page_log`: per-queue colour vs mono pages and last colour job, with user, host, sides
and media from the custom `PageLogFormat`. This exists only because the Pi's CUPS sees every job.
Once clients print straight to the printers, **CUPS never sees those jobs** and the log is empty or partial.

| Option | What you keep | What you lose | Effort |
|---|---|---|---|
| **B1. SNMP counters to HA** (recommended) | Totals, colour/mono/duplex deltas over time, graphs, "no colour for N days" | Who printed what, job names | S: HA Brother integration already planned in `docs/home-assistant.md` gives ink; counters need a few `snmp` sensors or reuse printer-care's decoder |
| B2. SNMP counters to Prometheus | Same, with retention and alerting | Same | M (needs an exporter or textfile job) |
| B3. Keep CUPS on TrueNAS as the print server for the family and keep `page_log` | Full per-job history | Defeats direct printing | M, and contradicts the goal |
| B4. Drop it | Nothing | Everything | S |

Recommendation: **B1.** Per-job attribution is a nice-to-have in a four-person household. printer-care's
`status` already shows the counters, so the data exists for B1 with no new collector (cron the `status` line
into a log if HA is not wanted). Dropping `history` from the CLI is optional; it just reports an empty log.
Existing `page_log` is worth copying off the Pi before it goes (one `scp`, S) so past totals survive.

## 3. Queue defaults (toner-saver, duplex, glossy photo)

Today these live in the Pi's CUPS queues (`black`, `colour`, `colour-photo`) and the Mac queues copied from them.
Direct printing moves them to the client.

| Option | How | Pros | Cons | Effort |
|---|---|---|---|---|
| **C1. Client presets + `print` skill** (recommended) | macOS/iOS: saved presets per printer (toner-saver, duplex); the `print` skill already sets options on `lp`, so just point it at the printers' IPP queues | No server, matches "direct" goal | Windows/Android users must set duplex themselves; photo preset = media/quality per app | S |
| C2. Keep a CUPS queue on TrueNAS/optiplex990 with the defaults | `lpadmin -o sides=two-sided-long-edge -o print-quality=...` | Defaults for everyone, one place | CUPS back in the print path, one more thing to keep running | M |
| C3. Printer-side defaults | Brother web UI, e.g. toner-save, 2-sided as default | Applies to everyone, even AirPrint | Not all options are settable as defaults; overridden per job by clients; photo preset not applicable | S |

Recommendation: **C3 for toner-saver and duplex where the web UI allows, C1 for the photo preset.** Note the
rest of the family likely never sets options, so C3 matters most for them. *Verify* which defaults the HL-L2350DW
and DCP-T780DW expose.

## 4. Sharing (AirPrint, Mopria, Windows)

The Pi shares the queues through CUPS (DNS-SD advertised once, since `ipp-usb` advertising is disabled).
Both printers are Wi-Fi capable and speak IPP Everywhere themselves.

| Option | How | Pros | Cons | Effort |
|---|---|---|---|---|
| **D1. Direct IPP/AirPrint/Mopria** (recommended) | Nothing to run; add printers from Bonjour/IPP URL `ipp://colour.lab.riera.co.uk/ipp/print` | Zero infrastructure; macOS, iOS, Android and Windows 10+ all support IPP driverless | Depends on printers waking from sleep and Wi-Fi quality: exactly what F2/F4 measure; Bonjour does not cross VLANs/subnets without an mDNS reflector | S |
| D2. Samba/WSD from a server | CUPS + Samba, or wsdd | Old Windows clients | Needs CUPS back; Windows 10+ does not need it | M |
| D3. mDNS reflector | avahi reflector on the router/host if printers are on another subnet | Fixes discovery only | Only if needed (*verify* the subnet) | S |

Recommendation: **D1.** Only revisit D2 if a specific Windows machine fails the F4 test.

## 5. Name and `print` skill

- `printer.lab.riera.co.uk` currently resolves to the Pi. After the move, either point it at the host with the
  surviving CUPS (A2/A3, C2) or retire it and use `black.lab.riera.co.uk` / `colour.lab.riera.co.uk`. Retire is
  cleaner; keep a CNAME for a month as the rollback signpost. DNS is a gate (needs Marc): effort S.
- The `print` skill's `black`/`colour` Mac queues currently go through the Pi. Repoint to
  `ipp://black.lab.riera.co.uk/ipp/print` and `ipp://colour.lab.riera.co.uk/ipp/print` (the F4 test queues are
  the rehearsal). The skill's markdown-to-PDF rendering is client-side already, so only the queue URI changes. S.
- Order: F4 test queues work, then repoint, then (after a week of normal use, per F5) switch the Pi off.

## Open questions for Marc

1. Is optiplex990 staying as a long-lived box? It decides A3 vs A2.
2. Is per-job history (who printed) wanted at all? If yes, B3/C2 keep CUPS and the Pi's removal shrinks to
   "move CUPS to a server".
3. Any Windows client? It decides whether D2 is ever needed.
4. Do the printers sit on the same subnet as clients and HA? It decides D3.

## Not done / not verified

No access to the Pi or printers this session. Printer capability claims (PostScript acceptance, settable
defaults, subnet) are inferences and marked *verify*; run F4 first.
