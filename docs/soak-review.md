# F2 soak: the weekly review command

Task <https://familia.riera.co.uk/tasks/3711>. Read-only: one GET per metric to Prometheus; starts no monitor, touches no printer.

## Each week (Marc, from the Mac on the LAN)
```sh
cd ~/Development/Project/printer-care && mkdir -p wifi-test/soak-bundles && wifi-test/soak-review.py --save wifi-test/soak-bundles/$(date +%F).json
```
Exit code: 0 GO, 1 KEEP SOAKING, 2 NO-GO, 3 input error. Add `--md > docs/soak-weekN-DATE.md` to keep the page in the repo.
Re-read an old week offline: `wifi-test/soak-review.py --from wifi-test/soak-bundles/2026-11-04.json`.

## Thresholds (per Wi-Fi printer; the wired Pi is a control, shown not judged)
| Check | Pass |
|---|---|
| ICMP success | >= 99.9 % |
| :631 success | >= 99.9 % |
| Longest ICMP / :631 outage | <= 300 s |
| ICMP RTT p95 | <= 50 ms |
| Soak length | >= 28 days since 2026-10-21 (`--soak-start`, `--min-days`) |

GO needs every check PASS and 28 days. A FAIL before day 28 reads KEEP SOAKING; a FAIL at or after day 28 reads NO-GO; missing data is never GO.
Weeks 1 and 2 (`docs/soak-week*.md`) suggest the RTT p95 threshold is unattainable over Wi-Fi power-save; recalibrate it in `THRESHOLDS`
(top of the script) only as a deliberate decision, not to turn a run green. The F4 weekly test print is a manual line in the output.
Tests: `make test` (sample logs are synthesised in `tests/test_soak_review.py`).
