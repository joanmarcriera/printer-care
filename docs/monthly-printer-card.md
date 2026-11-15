# Printer monthly card (5 minutes, first Saturday)

Colour printer (ink tank) and black printer (laser). A weekly keep-alive page already prints by itself, so you do **not** need to print colour "to keep it alive".

| # | Chore | How | Done |
|---|---|---|---|
| 1 | **Ink glance** | Look at the 4 tank windows on the colour printer: ink must be above the lower line. Or ask the Pi: `printer-care status` (ink and toner %, "low" under 15 %). Refill to the line only. After refilling, answer the on-screen refill prompt: `Settings > Ink > Ink Volume`. | [ ] |
| 2 | **Nozzle check, only if a print looked streaky or faded** | `Settings > Maintenance > Improve Print Quality > Check Print Quality`. Unbroken lines = fine, stop here. | [ ] |
| 3 | **Clean, only if the check sheet has gaps** | `Settings > Maintenance > Improve Print Quality > Cleaning`, pick Black or Colour (not All) and start at Normal. Re-run the check. Stronger levels only if gaps remain. Never "just in case": cleaning wastes ink and fills the waste-ink box. Two cleans in a row without improvement: stop and tell Marc. | [ ] |
| 4 | **Dust** | Switch off with the power button only, never at the wall (the head must park and cap). Wipe the outside and paper tray with a dry cloth. Nothing sprayed on or inside. | [ ] |
| 5 | **Paper** | Plain A4 in the paper tray of each printer, stack flat, below the limit mark, fresh pack stored flat and closed. Photo paper stays in its bag. | [ ] |
| 6 | **Mono toner** | `printer-care status` shows toner and drum. Swap only when the panel says Replace or print goes pale. | [ ] |
| 7 | **Anything odd** | `printer-care jobs` shows stuck jobs; `printer-care cancel-stuck` clears jobs older than an hour after asking y/N. Wrong or missing colour, error lights, noises: write it on the back of this card for Marc. | [ ] |

The menu paths come from the `printer-care care` cheat-sheet, which says they are general Brother knowledge and not checked against this exact firmware (the Reset menu is cited from Brother in docs/brother-webui-login.md); menu names vary by firmware. If a menu is not where the card says, use the panel search or the Brother guide at <https://support.brother.com>. Marc runs the printer-care commands on the print Pi; everyone else only reads the tank windows and uses the panel.
