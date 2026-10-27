# Phase F6 checklist: decommission the printer Pi

Task <https://familia.riera.co.uk/tasks/3716>. **Prepared 2026-10-27, nothing applied.** Do this only after F5
(<https://familia.riera.co.uk/tasks/3715>, `docs/cutover-runbook.md`) has run a full week with no Pi in the path.
Facts about the Pi from homelab `docs/hosts/printer.md` (192.168.0.179, `ssh printer`, Pi-hole reservation on host `pihole` 192.168.0.4).

## 0. Gate: confirm the week was clean

- [ ] Family printed normally for 7 days, no complaint, no rollback used.
- [ ] printer-care ran from optiplex990: `ssh optiplex990 'journalctl -u printer-care --since "-7d" | tail'` shows `check` runs, exit 0.
- [ ] No job reached the Pi in the week: `ssh printer 'sudo tail -n 20 /var/log/cups/page_log'` has nothing newer than the F5 cutover date.
- [ ] Both printers on Wi-Fi with stable reservations (they are .10 and .11; confirm in Pi-hole before touching DHCP).

## 1. Keep the F3 backup (do not delete)

F3 backup = `~pi/cups-backup-2026-10-18.tgz` plus the F5 one (`cups-before-f5-<date>.tgz`) and page_log copies. Copy them off the
Pi first, then verify: `scp printer:cups-*.tgz ~/Development/_inbox/printer-pi-backup/ && tar tzf ~/Development/_inbox/printer-pi-backup/*.tgz | head`.
Also keep `~pi/printer/` (Codex workspace: `OPERATIONS.md`, `.env` is secret, mode 600, copy only to a private location, never print it).

## 2. Physical (Marc, in the office)

1. Print one last page from each printer's panel or AirPrint to prove they stand alone.
2. Unplug USB from both printers, then power off the Pi (`ssh printer 'sudo shutdown -h now'` first, wait for the LED to stop, then pull power).
3. Do NOT wipe the SD card yet; shelf it for a month as the rollback.
4. Re-run the Wi-Fi smoke: `bash wifi-test/verify.sh net` (from the Mac) and one test page per printer. Exit 0 = PASS.
   Note: printers may have been using USB as a wake source; if one sleeps harder with USB unplugged, record it in the task.

## 3. DNS and DHCP (gate: Pi-hole is shared infrastructure, Marc applies)

Pi-hole `pihole` (192.168.0.4), config `dhcp.hosts` and `dns.hosts` (edited via `pihole-FTL --config`, see `docs/hosts/printer.md`).
Take a backup first: `ssh pihole 'sudo cp /etc/pihole/pihole.toml /etc/pihole/pihole.toml.bak-$(date +%F)-printer-pi'`.
- Remove the `dc:a6:32:4d:9a:1e` -> .179 `printer` reservation from `dhcp.hosts`. Mind: **a duplicate IP in dhcp.hosts breaks dnsmasq on :53**; validate before restart.
- `printer.lab.riera.co.uk`: per `docs/pi-job-options.md` section 5, either delete the record, or for one month keep it as a CNAME to
  `colour.lab.riera.co.uk` as a signpost, then remove. Recommended: delete now, since no client should use it after F5.
- Check: `dig +short printer.lab.riera.co.uk @192.168.0.4` (empty or the chosen target), `dig +short colour.lab.riera.co.uk @192.168.0.4` still `192.168.0.11`, `black.lab...` still `192.168.0.10`.
- DNS answering from Pi-hole (`dig +short example.com @192.168.0.4` non-empty) after the restart.

## 4. Docs and tools to update (all prepared as a list; edit when applying)

| Where | Change |
|---|---|
| homelab `docs/hosts/printer.md` | Mark the host retired with the date; move the Addressing/Print service/Clients sections to "Historical"; new section "Printing is direct over IPP: `ipp://black.lab...`, `ipp://colour.lab...`"; keep the web-UI-login research (task 3709) |
| homelab `.claude/skills/print-server-ops/SKILL.md` | Rewrite for direct IPP + printer-care on optiplex990; drop ipp-usb/USB sections or move to an appendix; keep the Brother gotchas that still apply (sleep, URF) |
| `~/.claude/skills/print/SKILL.md` (claude-config repo, `make zip-skills` after) | Already repointed in F5; final check that no `printer.lab`/Pi text remains |
| This repo `README.md` | Requirements and install text say "Raspberry Pi"/USB: reword to "any Linux host with CUPS"; mention empty `COLOUR_USB_ID` for network hosts |
| This repo `docs/home-assistant.md`, `homeassistant/` | `grep -rn '179\|printer.lab'` returned nothing on 2026-10-27; re-run, and confirm the HA integration targets `colour.lab`/`black.lab` |
| homelab `docs/inventory/` | `cd ~/Development/Project/homelab && bin/inventory && git diff docs/inventory/`; if the Pi is listed by hand in `services-annotations.tsv`, remove it there. Exit 2 means a host was unreachable: expected for the Pi only if it is still in `HL_HOSTS` (it is not by default) |
| homelab ADR | Record the outcome in `docs/decisions/` from `000-template.md` (the DECIDE task <https://familia.riera.co.uk/tasks/3714> may already have it) |
| `~/.ssh/config` | Remove or comment the `printer` alias after the SD card is shelved |

## 5. Close out

- [ ] `printer-care status` on optiplex990 still shows counters and a next-keep-alive date after the Pi is gone.
- [ ] Vikunja: close F5/F6 and the DECIDE task with evidence; supersede <https://familia.riera.co.uk/tasks/3708> (the stale PPD died with the Pi). 3708's script then does not need to run.
- [ ] Update `PROJECT_STATE.md`/memory `server-inventory` (Pi gone).

## Rollback after power-off

Power the Pi, replug USB, restore the Pi-hole reservation from the backup file, `systemctl enable --now ipp-usb`, `cupsenable` the queues,
re-add the Mac queues as `ipp://printer.lab.riera.co.uk:631/printers/<queue>`. Hence the one-month shelf for the SD card.
