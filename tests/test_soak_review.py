#!/usr/bin/env python3
"""Tests for wifi-test/soak-review.py over synthetic sample logs (no network).
Usage: python3 tests/test_soak_review.py   (exit 0 = pass)"""
import datetime as dt
import importlib.util
import io
import json
import os
import contextlib
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("soak", os.path.join(HERE, "..", "wifi-test", "soak-review.py"))
soak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(soak)

START = dt.datetime(2026, 10, 21, tzinfo=dt.timezone.utc)
END = int(dt.datetime(2026, 11, 18, 12, tzinfo=dt.timezone.utc).timestamp())  # day 28.5
T0 = END - 7 * 86400


def probe(step, n, bad=()):
    """n samples every `step` s from T0; indexes in `bad` fail."""
    return [[T0 + i * step, 0.0 if i in bad else 1.0] for i in range(n)]


def bundle(black_icmp, colour_icmp, rtt_black=0.03, rtt_colour=0.03, black_ipp=None, colour_ipp=None):
    n = 7 * 86400 // 60
    ok_ipp = probe(60, n)
    rtt = lambda v: [[T0 + i * 60, v] for i in range(n)]
    return {"end": END, "days": 7, "series": {
        "icmp": {"black": black_icmp, "colour": colour_icmp, "pi": probe(60, n)},
        "ipp": {"black": black_ipp or ok_ipp, "colour": colour_ipp or ok_ipp, "pi": ok_ipp},
        "rtt": {"black": rtt(rtt_black), "colour": rtt(rtt_colour), "pi": rtt(0.0003)}}}


TARGETS = dict(soak.DEFAULT_TARGETS)
N = 7 * 86400 // 60


class Stats(unittest.TestCase):
    def test_success_and_longest_outage(self):
        pct, fails, n, longest = soak.success_stats(probe(15, 1000, bad={10, 11, 12, 500}))
        self.assertEqual((fails, n), (4, 1000))
        self.assertAlmostEqual(pct, 99.6)
        self.assertEqual(longest, 45)          # 3 consecutive 15 s samples

    def test_no_failures_and_empty(self):
        self.assertEqual(soak.success_stats(probe(60, 10))[3], 0)
        self.assertIsNone(soak.success_stats([]))

    def test_percentile(self):
        self.assertEqual(soak.percentile(list(range(1, 101)), 95), 95)
        self.assertIsNone(soak.percentile([], 95))


class Verdicts(unittest.TestCase):
    def run_eval(self, b, now=None):
        return soak.evaluate(b, TARGETS, START, 28, now)

    def test_all_good_after_28_days_is_go(self):
        r = self.run_eval(bundle(probe(60, N), probe(60, N)))
        self.assertEqual(r["overall"], "GO")
        self.assertEqual(r["rows"]["pi"]["verdict"], "CONTROL")

    def test_good_but_too_early_keeps_soaking(self):
        early = int(dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc).timestamp())
        r = self.run_eval(bundle(probe(60, N), probe(60, N)), now=early)
        self.assertEqual(r["overall"], "KEEP SOAKING")

    def test_high_rtt_blocks_go(self):
        r = self.run_eval(bundle(probe(60, N), probe(60, N), rtt_black=1.4))
        self.assertEqual(r["rows"]["black"]["verdict"], "NO-GO")
        self.assertEqual(r["rows"]["colour"]["verdict"], "GO")
        self.assertEqual(r["overall"], "NO-GO")
        self.assertIn("ICMP RTT p95 <= 50 ms", r["rows"]["black"]["failed"])

    def test_long_outage_fails(self):
        bad = set(range(100, 100 + 7))          # 7 min of failed 60 s probes
        r = self.run_eval(bundle(probe(60, N, bad), probe(60, N)))
        self.assertIn("longest ICMP outage <= 300 s", r["rows"]["black"]["failed"])

    def test_ipp_refusal_run_fails(self):
        r = self.run_eval(bundle(probe(60, N), probe(60, N), black_ipp=probe(60, N, set(range(0, 3000)))))
        self.assertEqual(r["rows"]["black"]["verdict"], "NO-GO")

    def test_failures_before_day_28_are_only_keep_soaking(self):
        mid = int(dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc).timestamp())
        r = self.run_eval(bundle(probe(60, N), probe(60, N), rtt_black=1.4), now=mid)
        self.assertEqual(r["rows"]["black"]["verdict"], "KEEP SOAKING")

    def test_missing_data_never_go(self):
        b = bundle(probe(60, N), probe(60, N))
        b["series"]["rtt"].pop("colour")
        self.assertEqual(self.run_eval(b)["rows"]["colour"]["verdict"], "KEEP SOAKING")


class Cli(unittest.TestCase):
    def run_main(self, b, *extra):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(b, f)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = soak.main(["--from", f.name, *extra])
        os.unlink(f.name)
        return rc, out.getvalue()

    def test_exit_codes_and_one_page(self):
        rc, out = self.run_main(bundle(probe(60, N), probe(60, N)))
        self.assertEqual(rc, 0)
        self.assertIn("OVERALL: GO", out)
        self.assertLess(len(out.splitlines()), 40)       # one page
        rc, out = self.run_main(bundle(probe(60, N), probe(60, N), rtt_colour=0.2))
        self.assertEqual(rc, 2)
        self.assertIn("FAIL  ICMP RTT p95 <= 50 ms", out)
        self.assertIn("Manual (not auto-judged)", out)

    def test_markdown_header(self):
        _, out = self.run_main(bundle(probe(60, N), probe(60, N)), "--md")
        self.assertTrue(out.startswith("# F2 Wi-Fi soak review"))

    def test_bad_input_rc3(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(soak.main(["--from", "/nonexistent.json"]), 3)


if __name__ == "__main__":
    unittest.main()
