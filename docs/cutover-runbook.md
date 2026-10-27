# Phase F5 runbook: cut clients over to Wi-Fi printing and move printer-care off the Pi

Task <https://familia.riera.co.uk/tasks/3715>. **Prepared 2026-10-27, nothing applied.** Every step below is a
command for Marc to run; each is reversible until F6 (<https://familia.riera.co.uk/tasks/3716>).
Inputs: `docs/pi-job-options.md` (the options; this runbook assumes its recommendations), `docs/wifi-test-plan.md` (F4).

## 0. Preconditions (stop if any is false)

- [ ] F2 go/no-go (<https://familia.riera.co.uk/tasks/3711>) says GO for **each** printer. A NO-GO printer keeps its USB path: skip its rows below.
- [ ] F4 test matrix (<https://familia.riera.co.uk/tasks/3713>) cases 1-9 PASS, including case 4 (after overnight sleep).
- [ ] DECIDE (<https://familia.riera.co.uk/tasks/3714>) chose the keep-alive home. This runbook uses **A3: optiplex990** (`marc@192.168.0.234`, plain Debian). If A2 (TrueNAS container) was chosen, replace section 3 only.
- [ ] Backup exists: `ssh printer 'sudo tar czf ~/cups-before-f5-$(date +%F).tgz /etc/cups /var/lib/printer-care /etc/printer-care.conf'` then `scp` it off the Pi. Copy `/var/log/cups/page_log*` too (past totals).

## 1. Move printer-care (do this first: it has a clock to carry)

On the Pi, note the state: `sudo printer-care status` and `sudo cat /var/lib/printer-care/state`.

On optiplex990 (this repo, branch with the empty-`COLOUR_USB_ID` change, commit in section "Code change" below):

```sh
sudo apt install cups cups-client cups-ipp-utils snmp curl      # cups daemon needed for a local queue (A2/A3)
make install HOST=optiplex990                                    # from the repo checkout on the Mac
ssh optiplex990 'sudo lpadmin -p colour -E -v ipp://colour.lab.riera.co.uk/ipp/print -m everywhere -D "Colour keep-alive (local)"'
ssh optiplex990 'sudoedit /etc/printer-care.conf'                # see values below
```
Config values (`/etc/printer-care.conf`, mode 600):
```
COLOUR_HOST=colour.lab.riera.co.uk
COLOUR_QUEUE=colour
COLOUR_USB_ID=                      # empty: no USB check on a network host
BLACK_HOST=black.lab.riera.co.uk
BLACK_USB_ID=
HA_WEBHOOK_URL=<same value as the Pi's conf; copy it host to host, do not print it>
```
Carry the clock: `scp pi:/var/lib/printer-care/state` into `/var/lib/printer-care/state` on optiplex990 (or skip it:
worst case is one extra keep-alive page after 7 days).

Verify (evidence for the task comment):
```sh
ssh optiplex990 'sudo printer-care status'          # colour counter + ink read, "USB ... unknown"
ssh optiplex990 'sudo printer-care check --dry-run' # exit 0, "would print keep-alive on queue colour"
ssh optiplex990 'systemctl list-timers printer-care.timer'
```
Colour page proof, only after the Pi's own timer is disabled (one writer): `ssh optiplex990 'sudo printer-care keepalive --force'`
(it refuses when not due, so `--force`; costs one near-ink-free page); counter must rise, job must leave `lpstat -o`.
Then on the Pi: `sudo systemctl disable --now printer-care.timer` (**not** uninstall: rollback keeps it).

## 2. Repoint clients

| Client | Action | Check |
|---|---|---|
| Mac | `lpadmin -x black; lpadmin -x colour; lpadmin -x colour-photo` then add `black` = `ipp://black.lab.riera.co.uk/ipp/print`, `colour` = `ipp://colour.lab.riera.co.uk/ipp/print` with `-m everywhere`. Re-run `defaults write org.cups.PrintingPrefs UseLastPrinter -bool false` and `lpoptions -d black`. Keep old names so the skill needs no change. | `lpstat -v` shows hostnames, `print.sh --dry-run` works, one real page each |
| `print` skill | No script change if the queue names stay `black`/`colour`. Update `SKILL.md` text: path is now direct IPP, delete "Never print to the printers' own Wi-Fi IPs: the Pi is the print path", and the Pi/`printer.lab` mentions. Photo preset: add `colour-photo` as a Mac-only queue with `-o media-type=photographic-glossy -o print-quality=5`. | `grep -n 'printer.lab\|Pi' ~/.claude/skills/print/SKILL.md` empty |
| iPhone/iPad | Remove the Pi-advertised printers; AirPrint now discovers the two printers directly (same subnet: confirm with F4 case 6) | print a page from Safari |
| Android | Default Print Service or Brother app, discovers via mDNS (F4 case 7) | one page |
| Windows | Add printer by IPP URL `ipp://colour.lab.riera.co.uk/ipp/print` (F4 case 8) | one page |
| Home Assistant | No change yet: HA reads SNMP/IPP from `colour.lab`/`black.lab`, not the Pi (confirm in `homeassistant/`) | wallboard still green |

Defaults (toner-saver, duplex) per `docs/pi-job-options.md` section 3: set in each printer's web UI where offered (needs the web
password, task <https://familia.riera.co.uk/tasks/3709>).

## 3. Disable (not remove) ipp-usb on the Pi

Only after sections 1-2 verified. Keeps the rollback.
```sh
ssh printer 'sudo systemctl disable --now ipp-usb'   # the colour/colour-photo queues stop working: expected
ssh printer 'sudo cupsdisable colour colour-photo black'   # so nothing prints to the Pi by accident
```
Do **not** unplug USB, remove queues, or change DNS: the Pi stays powered with USB connected for one week.

## 4. Rollback (any time in the week)

```sh
ssh printer 'sudo systemctl enable --now ipp-usb; sudo cupsenable colour colour-photo black; sudo systemctl enable --now printer-care.timer'
ssh optiplex990 'sudo systemctl disable --now printer-care.timer'
# Mac: re-add queues as ipp://printer.lab.riera.co.uk:631/printers/<queue> (the old commands, docs/hosts/printer.md Clients)
```

## 5. The week: done criteria (task text)

- A week of normal family printing without the Pi in the path: no complaint, `lpstat -o` empty on the Mac, printers' counters rising (SNMP).
- printer-care keep-alive ran from its new home: `ssh optiplex990 'journalctl -u printer-care --since "-7d"'` and the state file's last-run date updated.
  If colour was printed daily the keep-alive legitimately never fires: then evidence = the daily `check` finding a risen counter.
- Then proceed to F6.

## Code change made for this runbook

`COLOUR_USB_ID`/`BLACK_USB_ID` may now be set empty = no USB check (`usb_present` returns `unknown`). Before this, any host
with `lsusb` but without the USB printer returned `no` and **skipped the keep-alive**. Test added in `tests/run.sh` (112 pass).
