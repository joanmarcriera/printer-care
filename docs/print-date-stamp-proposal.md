# Proposal: corner date stamp in the print skill

Task <https://familia.riera.co.uk/tasks/6917>. Status: **proposal, not applied.** The skill lives in claude-config
(`skills/print/`, symlinked to `~/.claude/skills/print`); this repo only holds the patch.

## What the skill does today (read-only survey, 2026-11-15)
`skills/print/scripts/print.sh` has four paths and none adds a date: markdown/text/log go pandoc -> weasyprint -> `lp`;
PDF and images go straight to `lp`; `--mono` hands plain text to the CUPS text filter. Styles are `styles/*.css`, @page margin 12 mm.

## The patch
`ops/print-skill-date-stamp.patch` (in this repo) adds:
- `scripts/stamp.py` (new): stamps `YYYY-MM-DD` in 8 pt Helvetica, 14 mm from the right and 7 mm from the top, on every page
  (pypdf + reportlab, both installed for the system `python3`).
- `print.sh`: every path now ends in a PDF that is stamped before `lp`. Markdown/text: stamp the weasyprint PDF. PDF input: stamp a
  copy (the original is untouched). Images: converted to an A4 PDF (fit, centred, 90 %) first. `--mono`: `cupsfilter` renders the same
  text (cpi and lpi kept) to PDF, then stamped. `--no-stamp` opts out. If stamping fails nothing is printed (exit 3, message says
  `--no-stamp` skips it) so a job never silently loses the date.

## Verified (scratch copy, `--dry-run`, nothing printed)
- md, txt (`--mono`), pdf and png each produced a 1-page PDF whose text contains today's date (`pdftotext | grep`); `--no-stamp` produced none.
- A first version failed on pypdf 7 (`replace_contents` removed); the failure path refused to print, then the fix passed.
- `git apply --check` in claude-config: rc=0.
- Visual check of the md page: date sits top-right, clear of the 12 mm text margin.

## Apply (one command, from claude-config on a branch)
```sh
cd ~/Development/Project/claude-config && git apply -p1 --directory=skills/print ~/Development/_worktrees/printer-care4/ops/print-skill-date-stamp.patch
```
(Once this branch is merged use `~/Development/Project/printer-care/ops/print-skill-date-stamp.patch`.) Then add one line to
`skills/print/SKILL.md` ("every page is stamped with the date; `--no-stamp` to skip") and commit.

## Notes and limits
- `--mono` now goes through PDF, so a `--mono` print is no longer the raw CUPS text path; cpi/lpi are passed to `cupsfilter` but not
  compared on paper. Marc to eyeball one `--mono` print (a gate: this drive does not print).
- A claude.ai skill `print-with-date-stamp` also exists; this proposal makes the local skill do the same without it.
- Stamp position was chosen to stay inside the printable area of the HL-L2350DW and DCP-T780DW; check on the first real print.
