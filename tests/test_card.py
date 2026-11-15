#!/usr/bin/env python3
"""Every command or menu path the family chore card puts in backticks must exist in printer-care
(subcommand in main()'s case list, menu path in cmd_care) or in a Brother page cited in docs/.
Usage: python3 -I tests/test_card.py   (exit 0 = pass)"""
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


CARD = read("docs", "monthly-printer-card.md")
SCRIPT = read("printer-care")
CITED = SCRIPT + read("docs", "brother-webui-login.md")
SPANS = re.findall(r"`([^`]+)`", CARD)
main_body = SCRIPT[SCRIPT.index("\nmain() {"):]
SUBCMDS = set(re.findall(r"^\s+([a-z-]+(?:\|[a-z-]+)*)\)\s", main_body, re.M))
SUBCMDS = {c for group in SUBCMDS for c in group.split("|")}


class Card(unittest.TestCase):
    def test_has_spans(self):
        self.assertGreaterEqual(len(SPANS), 5)

    def test_every_span_is_known(self):
        for s in SPANS:
            with self.subTest(span=s):
                if s.startswith("printer-care "):
                    sub = s.split()[1]
                    self.assertIn(sub, SUBCMDS)
                    for flag in re.findall(r"--[a-z-]+", s):
                        self.assertIn(flag, SCRIPT)
                elif ">" in s:
                    self.assertIn(s, CITED, "menu path not found in printer-care or cited Brother docs")
                else:
                    self.fail("unclassified backtick span: " + s)

    def test_subcommands_found(self):
        for c in ("status", "jobs", "cancel-stuck"):
            self.assertIn(c, SUBCMDS)

    def test_ink_threshold_matches_script(self):
        self.assertRegex(SCRIPT, r"LOW_INK_PERCENT\(15\)")
        self.assertIn("under 15 %", CARD)


if __name__ == "__main__":
    unittest.main()
