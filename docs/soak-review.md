# F2 soak: the weekly review command

Task <https://familia.riera.co.uk/tasks/3711>. Read-only: GET queries to Prometheus; starts no monitor, touches no printer.

## Each week (Marc, from the Mac on the LAN)
```sh
cd ~/Development/Project/printer-care && mkdir -p wifi-test/soak-bundles && wifi-test/soak-review.py --days 28 --save wifi-test/soak-bundles/$(date +%F).json
```
`--days 28` looks at the whole soak so far, so an early bad week is never forgotten (Prometheus retention must cover it; if the query
returns less, the output says the data window is shorter). ICMP and RTT are fetched at the probe's own 15 s, :631 at 60 s, in chunks.
For a quick one-week look use plain `wifi-test/soak-review.py`: it prints a "not a final verdict" note and can never say GO.
Add `--md > docs/soak-weekN-DATE.md` to keep the page in the repo. Re-read saved weeks offline, merged:
`wifi-test/soak-review.py --from wifi-test/soak-bundles/A.json --from wifi-test/soak-bundles/B.json`.

Exit code: 0 GO | 1 KEEP SOAKING (nothing failing yet) | 2 NO-GO | 3 input error | 4 KEEP SOAKING but a check already fails.
`--target NAME=HOST` takes the exact host in the Prometheus `instance` label; a target matching 0 or 2+ series prints a warning on stderr.

## Thresholds (per Wi-Fi printer; the wired Pi is a control, shown not judged)
| Check | Pass | Source |
|---|---|---|
| ICMP success, :631 success | >= 99.9 % | go criteria in `docs/soak-week1-2026-10-28.md`, `docs/soak-week2-2026-10-31.md` |
| Longest ICMP / :631 outage | <= 300 s (5 min) | same |
| ICMP RTT p95 | <= 50 ms | same |
| Soak length and data window | >= 28 days | task wording "4+ weeks" in <https://familia.riera.co.uk/tasks/3711>; start 2026-10-21 (`--soak-start`, `--min-days`) |

GO needs every check PASS **and** a soak age and data window of 28 days. Before that, a FAIL reads KEEP SOAKING (exit 4); with a full
window, a FAIL reads NO-GO; missing data is never GO. Each Wi-Fi target must itself have a series spanning the window with >= 95 % of the expected samples (a Prometheus outage or a late-added target never reads as 100 % success). Outage = consecutive failed samples (each counts one probe step; a data gap does not
bridge two outages), so it is accurate to one step.
Weeks 1 and 2 suggest the RTT p95 threshold is unattainable over Wi-Fi power-save; recalibrate it in `THRESHOLDS` (top of the script)
only as a deliberate decision, not to turn a run green. The F4 weekly test print is a manual line in the output.
Tests: `make test` (24 tests, sample logs synthesised in `tests/test_soak_review.py`).
