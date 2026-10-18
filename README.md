# printer-care

A small bash tool for a Raspberry Pi (or any Linux box) acting as a CUPS print server for
two Brother printers over USB. Its main job: **stop the colour ink-tank printer's nozzles
drying out** by printing a tiny, nearly ink-free colour page whenever the printer has not
printed colour for N days.

```
$ printer-care status
Colour printer
  host                 colour-printer.example.lan
  USB (04f9:0767)      yes
  CUPS queue           colour: printer colour is idle.  enabled since ...
  pending jobs         0
  ink                  M 99%  C 99%  Y 99%  BK 99%
  counters             total 5 | colour 3 | mono 2 | duplex 0
  last colour          3 day(s) ago (2026-10-15 10:31)
  next keep-alive due  2026-10-22 10:31 (every 7d without colour)
```

## Why it works this way

Most "keep-alive" scripts watch the CUPS job log. That misses colour pages produced by
**copies, scans-to-print, Wi-Fi/AirPrint jobs straight to the printer, or another computer** -
and it wrongly assumes a queued job was actually printed. printer-care instead reads the
printer's **own colour page counter over SNMP** once a day. If the counter has risen, colour
was printed, whatever the source, and the clock restarts. Only if it has been flat for
`KEEPALIVE_DAYS` does it print a page - and then it **verifies itself**: the job must leave
the queue *and* the counter must rise, otherwise you get a notification (paper out? empty
tank? printer asleep?).

The keep-alive page is A4 with thin cyan/magenta/yellow bars and hairlines (a few dozen
microlitres of ink in total) plus one line of black text stamping date, host and counters.

## Requirements

- Debian/Raspberry Pi OS (tested design target: Debian 13 "trixie", bash 5.2, mawk) with CUPS
  (`lp`, `lpstat`), `snmp` (`snmpget`/`snmpwalk`), `cups-ipp-utils` (`ipptool`), `curl`, `usbutils` (`lsusb`)
  ```
  sudo apt install cups-client cups-ipp-utils snmp curl usbutils
  ```
- SNMP v2c enabled on the printers (Brother default community: `public`).
- bash >= 3.2 (also runs on macOS for `status`/dev), POSIX awk (no gawk extensions).
- **Brother-specific**: the colour counter is read from Brother's private OID
  `1.3.6.1.4.1.2435.2.3.9.4.2.1.5.5.10.0`. Verified on DCP-T780DW and HL-L2350DW;
  other Brother models likely work, other brands will not without code changes.

## Install

```
git clone <this repo> && cd printer-care
make test                       # shellcheck (if installed) + tests
make install HOST=my-print-pi   # needs ssh + sudo on the Pi
sudo $EDITOR /etc/printer-care.conf
sudo printer-care status
```

`make install` copies the script to `/usr/local/bin`, installs the config as
`/etc/printer-care.conf` (mode 600, only if absent), installs the systemd units and enables
`printer-care.timer` (daily ~10:30, `Persistent=true`, 15 min random delay). Nothing is run
from `/tmp` (often `noexec`). `make uninstall HOST=...` removes binary and units, keeping config and state.

### Enable the CUPS page log (for `history`)

In `/etc/cups/cupsd.conf`:

```
PageLogFormat %p %u %j %T %P %C %{job-originating-host-name} %{print-color-mode} %{sides} %{media} %{job-name}
```
then `sudo systemctl restart cups`. (CUPS 2.x default is empty = no page log.) `job-name`
is last because it may contain spaces. Per-page and `total` lines are both handled.
Debian's stock `/etc/logrotate.d/cups-daemon` rotates `/var/log/cups/*log` daily and keeps 7,
which silently deletes `page_log` history after a week. Narrow that glob to
`access_log error_log` and give `page_log` its own stanza (e.g. monthly, `rotate 24`, `copytruncate`).

### USB gotcha: Brother inkjets want IPP-over-USB, not the raw USB channel

The DCP-T780DW advertises `CMD:HBP,PJL,URF` in its USB device ID, so a driverless queue on
`usb://Brother/...` looks right, and CUPS reports every job as *completed*. Nothing prints.
Tested on 2026-10-18: the same Apple-raster (URF) file prints over the network via IPP, but on
the raw USB printer channel (interface class 7/1/2) the printer swallows it silently, whether
bare or wrapped in `@PJL ENTER LANGUAGE=URF`.

What works is the printer's **IPP-over-USB** interface (7/1/4) through
[`ipp-usb`](https://github.com/OpenPrinting/ipp-usb):

```ini
# /etc/ipp-usb/quirks/local.conf: keep other USB printers on the classic usb:// backend
[Brother HL-L2350DW*]
  blacklist = true
```

In `/etc/ipp-usb/ipp-usb.conf` set `dns-sd = disable` so the printer isn't advertised twice
(CUPS already shares the queue), then:

```sh
sudo systemctl unmask ipp-usb && sudo systemctl start ipp-usb
sudo lpadmin -p colour -v ipp://localhost:60000/ipp/print
```

Two traps:

- Without the blacklist, `ipp-usb` also claims any other IPP-USB-capable printer (the HL-L2350DW
  has a 7/1/4 interface too), and that printer's `usb://` queue hangs at "Waiting for printer".
- `ipp-usb status` (0.9.23) can panic and take the daemon down with it. A systemd drop-in with
  `Restart=on-failure` brings it back.

The laser works fine on the raw channel with `brlaser`. `printer-care` doesn't mind which path
a queue uses; its USB check only looks for the device with `lsusb`.

## Usage

| Command | What it does |
|---|---|
| `status` | USB presence, CUPS queue state, pending jobs, ink/toner/drum %, counters, next keep-alive due. Degrades to `n/a` where `lpstat`/`lsusb` are missing. |
| `check [--dry-run]` | What the timer runs: update the colour clock from the counter, verify the previous keep-alive, print a new one if due. |
| `keepalive [--force] [--dry-run]` | Print the keep-alive page now (without `--force` only if actually due). |
| `test-page colour\|black [--dry-run]` | Small test page. Black uses text only. |
| `jobs` | Pending and recently completed jobs. |
| `cancel-stuck [--yes]` | Cancel jobs older than 1 hour on both queues. |
| `history [days]` | Pages per queue from `page_log`: colour vs mono, last colour job. |
| `care` | Manual maintenance cheat-sheet (nozzle check, head cleaning, ink-counter reset after refill, laser toner/drum). |

`--dry-run` never prints, never writes state and never sends notifications; it logs what it would do.

Exit codes: `0` ok, `1` usage/config error, `2` a printer/host was unreachable (`status`),
`3` action needed or failed. For `check`, `3` means this run raised an alert: the 3rd (then every
7th) consecutive unreadable counter, a stuck or uncounted keep-alive, a missing USB device, or a
failed print. A failed run shows in `systemctl --failed`.

## Configuration

`/etc/printer-care.conf` (see [printer-care.conf.example](printer-care.conf.example)) is plain
`KEY=VALUE`, parsed with a whitelist and **never sourced or evaluated**. Environment variables
of the same name win over the file. Keys: `COLOUR_HOST`, `COLOUR_QUEUE`, `COLOUR_USB_ID`,
`BLACK_HOST`, `BLACK_QUEUE`, `BLACK_USB_ID`, `SNMP_COMMUNITY`, `KEEPALIVE_DAYS` (7),
`LOW_INK_PERCENT` (15), `HA_WEBHOOK_URL`, `PAGE_LOG`. Trailing `# comments` after whitespace are allowed; wrap a value in quotes to keep a literal ` #`.

State is `/var/lib/printer-care/state` (atomic KEY=VALUE writes). Test/override hooks:
`PRINTER_CARE_CONF`, `PRINTER_CARE_STATE_DIR`, `PRINTER_CARE_NOW`, `PRINTER_CARE_SNMP_FIXTURE`, `PRINTER_CARE_LPSTAT_O` (tests). The webhook URL is passed to curl on stdin so it does not appear in `ps`.

## How detection works

1. Read the counters blob (a hex string of `code 01 04 <uint32>` records ended by `FF`;
   codes `00` total, `01` mono, `02` colour, `06` duplex). A blob without a colour record is rejected.
2. Colour counter higher than stored -> record "colour changed now". First run seeds the clock.
3. The window start is the **later of the last colour change and the last keep-alive**. When
   `KEEPALIVE_DAYS` have passed since then, print. Because a keep-alive restarts the window, there is
   **at most one keep-alive per window** whatever goes wrong (SNMP down, job cancelled, counter flat),
   so a fault cannot burn paper.
4. After printing, the baseline counter is read fresh and stored. Once the job leaves the queue: counter
   above baseline -> verified; flat -> `keepalive_not_counted` (no reprint until the next window); baseline
   or counter unknown -> noted, not verified. Still queued after a whole window -> `keepalive_stuck`.
5. If `lpstat` itself fails the queue state is *unknown*: that run neither verifies nor prints.
6. Counter unreadable -> stored timestamps are used; `counter_unreadable` fires on the 3rd consecutive
   miss, then every 7th (10th, 17th, ...).
7. USB device missing -> skip and send `printer_absent`.

Ink and toner levels come from IPP `marker-levels`/`marker-names` (the standard Printer-MIB
supply levels report "unknown" on some Brother ink-tank models). The laser's drum percentage
is level/max from the Printer-MIB supplies row, rounded up (matches its web page).

Notification events: `keepalive_printed`, `keepalive_stuck`, `keepalive_not_counted`,
`keepalive_failed`, `counter_unreadable`, `printer_absent`.

## Home Assistant

Optional. Set `HA_WEBHOOK_URL` and printer-care POSTs
`{"event","printer","message","host"}`. Delivery failures are logged, never fatal.
Recipes (webhook automation, low-ink alerts, conditional dashboard card) are in
[docs/home-assistant.md](docs/home-assistant.md).

## Limitations

- Brother-specific counter OID; not tested beyond the two models above.
- No remote head-cleaning API: cleaning is a front-panel action (`printer-care care` lists the menus).
- It cannot tell you the tanks are physically empty - only that a keep-alive did not register.
- `cancel-stuck` needs GNU `date -d` (fine on Linux).
- Not a substitute for printing real colour occasionally; it only covers gaps.
- The colour counter can rise by more than the sheets that come out. In testing, raw-USB jobs
  that printed nothing were still counted. It is a reliable "colour was used" signal, not a
  sheet count.

## Development

`make test` runs shellcheck and `tests/run.sh` (pure bash, no framework): TLV decoding, the
decision table, clock logic, `check` scenarios against fixtures, page_log parsing, config/state
injection safety. Commits follow Conventional Commits; the changelog is generated with
[git-cliff](https://git-cliff.org) (`cliff.toml`).

## Licence

MIT - see [LICENSE](LICENSE).
